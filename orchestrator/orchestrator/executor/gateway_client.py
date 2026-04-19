"""
Gateway Client — authenticated MCP tool-call client.

Authenticates via Keycloak client-credentials flow, then makes
JSON-RPC 2.0 tool/call requests through the MCP gateway.

The client is intentionally kept stateless: each instance holds a
cached token that is refreshed on 401.  No persistent connection pool
is maintained so the client is safe to instantiate per-request.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
import structlog

log = structlog.get_logger("orchestrator.executor.gateway_client")

# ---------------------------------------------------------------------------
# Configuration (from environment, with sensible demo defaults)
# ---------------------------------------------------------------------------

_KEYCLOAK_REALM_URL = os.environ.get(
    "KEYCLOAK_REALM_URL", "http://keycloak:8080/realms/trading"
)
_GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://gateway:9000")

# Client credentials used by the orchestrator to authenticate with Keycloak
_CLIENT_ID = os.environ.get("ORCHESTRATOR_CLIENT_ID", "thesis-validator")
_CLIENT_SECRET = os.environ.get("ORCHESTRATOR_CLIENT_SECRET", "validator-secret-2024")

# Scopes the orchestrator needs to call all three backends through the gateway
_REQUIRED_SCOPES = "bloomberg:read risk:read research:read"

# How many seconds before token expiry to refresh proactively
_TOKEN_REFRESH_BUFFER_S = 30


class GatewayClient:
    """
    Thin wrapper around httpx that handles Keycloak authentication and
    JSON-RPC tool calls through the MCP gateway.

    Usage:
        async with GatewayClient() as client:
            result = await client.call_tool("bloomberg", "get_ref_data", {...})
    """

    def __init__(
        self,
        gateway_url: str = _GATEWAY_URL,
        keycloak_realm_url: str = _KEYCLOAK_REALM_URL,
        client_id: str = _CLIENT_ID,
        client_secret: str = _CLIENT_SECRET,
        timeout: float = 30.0,
    ) -> None:
        self._gateway_url = gateway_url.rstrip("/")
        self._keycloak_realm_url = keycloak_realm_url.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout = timeout

        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "GatewayClient":
        self._http = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def call_tool(
        self,
        server: str,
        tool: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Call an MCP tool on a backend server via the gateway.

        Automatically authenticates and refreshes the token as needed.

        Args:
            server:    Gateway route prefix ('bloomberg', 'risk', 'research').
            tool:      MCP tool name on the target server.
            arguments: Tool call arguments (JSON-serialisable dict).

        Returns:
            The parsed content from the MCP tool response.

        Raises:
            GatewayError: On HTTP errors or JSON-RPC error responses.
        """
        token = await self._get_token()
        payload = _build_jsonrpc_payload(tool, arguments)
        url = f"{self._gateway_url}/{server}"

        assert self._http is not None, "GatewayClient must be used as async context manager"

        response = await self._http.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )

        if response.status_code == 401:
            # Token may have expired mid-flight — force refresh and retry once
            self._access_token = None
            token = await self._get_token()
            response = await self._http.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )

        if response.status_code >= 400:
            raise GatewayError(
                f"Gateway returned HTTP {response.status_code} for "
                f"{server}/{tool}: {response.text[:200]}",
                status_code=response.status_code,
            )

        body = response.json()
        return _extract_result(body, server, tool)

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def _get_token(self) -> str:
        """Return a valid access token, fetching a new one if needed."""
        now = time.monotonic()
        if self._access_token and now < self._token_expires_at - _TOKEN_REFRESH_BUFFER_S:
            return self._access_token

        self._access_token, expires_in = await self._fetch_token()
        self._token_expires_at = now + expires_in
        return self._access_token

    async def _fetch_token(self) -> tuple[str, int]:
        """
        Perform Keycloak client-credentials grant.

        Returns (access_token, expires_in_seconds).
        """
        token_url = f"{self._keycloak_realm_url}/protocol/openid-connect/token"
        assert self._http is not None

        response = await self._http.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": _REQUIRED_SCOPES,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code >= 400:
            raise GatewayError(
                f"Keycloak token fetch failed (HTTP {response.status_code}): "
                f"{response.text[:200]}",
                status_code=response.status_code,
            )

        data = response.json()
        token = data.get("access_token")
        if not token:
            raise GatewayError(
                "Keycloak response did not contain access_token",
                status_code=response.status_code,
            )

        expires_in = int(data.get("expires_in", 300))
        log.debug("token_fetched", expires_in=expires_in, client_id=self._client_id)
        return token, expires_in


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class GatewayError(Exception):
    """Raised when the gateway returns an error response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------


def _build_jsonrpc_payload(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 tools/call request payload."""
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool,
            "arguments": arguments,
        },
    }


def _extract_result(body: dict[str, Any], server: str, tool: str) -> dict[str, Any]:
    """
    Extract the tool result from a JSON-RPC 2.0 response.

    MCP tools/call responses have the shape:
      {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "..."}]}}

    We parse the text content as JSON if possible, otherwise return it as-is.
    """
    if "error" in body:
        err = body["error"]
        raise GatewayError(
            f"{server}/{tool} returned JSON-RPC error {err.get('code')}: {err.get('message')}",
        )

    result = body.get("result", {})
    content = result.get("content", [])

    if not content:
        return result

    # MCP returns content as a list of typed blocks — extract first text block
    for block in content:
        if block.get("type") == "text":
            import json
            text = block.get("text", "")
            try:
                return json.loads(text)
            except (json.JSONDecodeError, ValueError):
                return {"raw_text": text}

    return result
