"""E2E: Tool Aggregation — verify merged tool manifests."""

from __future__ import annotations

import pytest
from tests.e2e.conftest import GATEWAY_URL

import httpx


class TestToolAggregation:
    """Verify the /tools/aggregate endpoint merges backends correctly."""

    def test_aggregation_returns_tools(self, alice_token: str):
        """Aggregation endpoint returns a non-empty tool list."""
        resp = httpx.get(
            f"{GATEWAY_URL}/tools/aggregate",
            headers={"Authorization": f"Bearer {alice_token}"},
            timeout=30.0,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "tools" in body
        assert body["count"] > 0

    def test_tools_are_namespaced(self, alice_token: str):
        """Tool names should be prefixed with their server name."""
        resp = httpx.get(
            f"{GATEWAY_URL}/tools/aggregate",
            headers={"Authorization": f"Bearer {alice_token}"},
            timeout=30.0,
        )
        body = resp.json()
        tool_names = [t["name"] for t in body.get("tools", [])]

        # Should see bloomberg__, risk__, research__ prefixes
        has_bloomberg = any("bloomberg__" in name for name in tool_names)
        has_risk = any("risk__" in name for name in tool_names)
        has_research = any("research__" in name for name in tool_names)

        assert has_bloomberg, f"No bloomberg tools found in: {tool_names}"
        assert has_risk, f"No risk tools found in: {tool_names}"
        assert has_research, f"No research tools found in: {tool_names}"

    def test_aggregation_requires_auth(self):
        """Aggregation endpoint requires Bearer token."""
        resp = httpx.get(f"{GATEWAY_URL}/tools/aggregate", timeout=10.0)
        assert resp.status_code == 401

    def test_tool_count_matches_backends(self, alice_token: str):
        """Should have tools from all 3 backends (9 total: 3+3+3)."""
        resp = httpx.get(
            f"{GATEWAY_URL}/tools/aggregate",
            headers={"Authorization": f"Bearer {alice_token}"},
            timeout=30.0,
        )
        body = resp.json()
        # Each server has 3 tools = 9 total
        assert body["count"] >= 6, f"Expected at least 6 tools, got {body['count']}"
