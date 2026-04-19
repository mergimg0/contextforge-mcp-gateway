"""E2E: Authentication flow — Keycloak → JWT → Gateway → Backend."""

from __future__ import annotations

import jwt
import pytest
from tests.e2e.conftest import get_token, gateway_call, GATEWAY_URL

import httpx


class TestAuthFlow:
    """Verify the complete authentication flow works end-to-end."""

    def test_alice_gets_valid_jwt(self, alice_token: str):
        """Alice can authenticate and gets a JWT with correct claims."""
        claims = jwt.decode(alice_token, options={"verify_signature": False})
        assert claims["sub"] is not None
        assert "desk_access" in claims or "realm_access" in claims

    def test_bob_gets_valid_jwt(self, bob_token: str):
        """Bob can authenticate and gets a JWT with correct claims."""
        claims = jwt.decode(bob_token, options={"verify_signature": False})
        assert claims["sub"] is not None

    def test_unauthenticated_request_rejected(self):
        """Request without Bearer token returns 401."""
        resp = httpx.post(
            f"{GATEWAY_URL}/bloomberg/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            timeout=10.0,
        )
        assert resp.status_code == 401

    def test_invalid_token_rejected(self):
        """Request with invalid JWT returns 401."""
        resp = httpx.post(
            f"{GATEWAY_URL}/bloomberg/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers={"Authorization": "Bearer invalid-token-here"},
            timeout=10.0,
        )
        assert resp.status_code == 401

    def test_alice_can_call_bloomberg(self, alice_token: str):
        """Alice can successfully call Bloomberg MCP through the gateway."""
        resp = gateway_call(
            alice_token, "bloomberg", "get_ref_data",
            {"tickers": ["AAPL"], "fields": ["PX_LAST"], "desk": "equities"},
        )
        assert resp.status_code == 200

    def test_alice_can_call_risk(self, alice_token: str):
        """Alice can successfully call Risk MCP through the gateway."""
        resp = gateway_call(
            alice_token, "risk", "calculate_var",
            {"desk": "equities", "metric": "var", "confidence": 0.99, "horizon_days": 1},
        )
        assert resp.status_code == 200

    def test_alice_can_call_research(self, alice_token: str):
        """Alice can successfully call Research MCP through the gateway."""
        resp = gateway_call(
            alice_token, "research", "search_research",
            {"query": "volatility", "max_results": 3},
        )
        assert resp.status_code == 200

    def test_nonexistent_route_returns_404(self, alice_token: str):
        """Request to unknown route returns 404."""
        resp = httpx.post(
            f"{GATEWAY_URL}/nonexistent/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers={"Authorization": f"Bearer {alice_token}"},
            timeout=10.0,
        )
        assert resp.status_code == 404
