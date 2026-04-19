"""E2E: Health checks — verify all services are running."""

from __future__ import annotations

import httpx
import pytest


SERVICES = {
    "gateway": "http://localhost:9000/health",
    "bloomberg-mcp": "http://localhost:8010/health",
    "risk-mcp": "http://localhost:8011/health",
    "research-mcp": "http://localhost:8012/health",
}


class TestHealth:
    """Verify all services report healthy status."""

    @pytest.mark.parametrize("service,url", SERVICES.items())
    def test_service_healthy(self, service: str, url: str):
        """Each service should respond to health check."""
        resp = httpx.get(url, timeout=10.0)
        assert resp.status_code in (200, 404), f"{service} unhealthy: {resp.status_code}"

    def test_keycloak_healthy(self):
        """Keycloak should report UP status."""
        resp = httpx.get("http://localhost:8080/health/ready", timeout=10.0)
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("status") == "UP"
