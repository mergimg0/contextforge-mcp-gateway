"""E2E test fixtures: Keycloak authentication helpers and Docker Compose management."""

from __future__ import annotations

import os
import subprocess
import time
from typing import Generator

import httpx
import pytest

KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://localhost:8080")
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:9000")
REALM = "trading"
TOKEN_URL = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token"

USERS = {
    "alice": {"username": "alice-pm", "password": "alice-demo-2024", "desk": "equities"},
    "bob": {"username": "bob-pm", "password": "bob-demo-2024", "desk": "rates"},
    "charlie": {"username": "charlie-pm", "password": "charlie-demo-2024", "desk": "equities"},
}


def get_token(user_key: str) -> str:
    """Obtain a Keycloak access token via direct access grant."""
    user = USERS[user_key]
    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "password",
            "client_id": "demo-agent",
            "username": user["username"],
            "password": user["password"],
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def gateway_call(token: str, route: str, tool: str, arguments: dict) -> httpx.Response:
    """Make an MCP tool call through the gateway."""
    return httpx.post(
        f"{GATEWAY_URL}/{route}/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )


@pytest.fixture(scope="session")
def alice_token() -> str:
    return get_token("alice")


@pytest.fixture(scope="session")
def bob_token() -> str:
    return get_token("bob")


@pytest.fixture(scope="session")
def charlie_token() -> str:
    return get_token("charlie")
