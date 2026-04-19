"""HTTP streaming proxy: forwards MCP requests to backend servers."""

from __future__ import annotations

import logging
from typing import Optional

import httpx
from fastapi import Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)


async def proxy_request(
    request: Request,
    backend_url: str,
    backend_path: str,
    backend_token: str,
    caller_sub: str,
    request_id: str,
    timeout: int = 30,
) -> StreamingResponse:
    """
    Forward an MCP request to a backend server with the exchanged token.

    Preserves:
    - Request body (JSON-RPC payload)
    - Content-Type header
    - X-Request-ID for distributed tracing
    - X-Caller-Sub for audit trail on backend
    """
    target = f"{backend_url.rstrip('/')}{backend_path}"
    body = await request.body()

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.request(
            method=request.method,
            url=target,
            content=body,
            headers={
                "Authorization": f"Bearer {backend_token}",
                "Content-Type": request.headers.get("Content-Type", "application/json"),
                "X-Caller-Sub": caller_sub,
                "X-Request-ID": request_id,
            },
        )

    # Forward response headers, filtering hop-by-hop headers
    excluded_headers = {"transfer-encoding", "connection", "keep-alive"}
    response_headers = {
        k: v for k, v in resp.headers.items() if k.lower() not in excluded_headers
    }

    return StreamingResponse(
        content=_iter_bytes(resp),
        status_code=resp.status_code,
        headers=response_headers,
        media_type=resp.headers.get("content-type", "application/json"),
    )


async def _iter_bytes(resp: httpx.Response):
    """Yield response body. For non-streaming responses, yield the full body."""
    yield resp.content
