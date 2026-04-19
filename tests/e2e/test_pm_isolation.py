"""E2E: PM Isolation — verify desk-based access control works end-to-end."""

from __future__ import annotations

import pytest
from tests.e2e.conftest import gateway_call


class TestPMIsolation:
    """Verify PM isolation enforced across all MCP servers."""

    def test_alice_equities_permitted(self, alice_token: str):
        """Alice (equities desk) CAN access equities data."""
        resp = gateway_call(
            alice_token, "bloomberg", "get_ref_data",
            {"tickers": ["AAPL"], "fields": ["PX_LAST"], "desk": "equities"},
        )
        assert resp.status_code == 200

    def test_alice_rates_denied(self, alice_token: str):
        """Alice (equities desk) CANNOT access rates desk data."""
        resp = gateway_call(
            alice_token, "bloomberg", "get_ref_data",
            {"tickers": ["AAPL"], "fields": ["PX_LAST"], "desk": "rates"},
        )
        # Should get an error — either 403 from gateway or error in JSON-RPC response
        body = resp.json()
        if resp.status_code == 200:
            # MCP JSON-RPC may return 200 with error payload
            assert "error" in body, "Expected PM isolation denial for rates desk"
        else:
            assert resp.status_code in (403, 500)

    def test_bob_rates_permitted(self, bob_token: str):
        """Bob (rates desk) CAN access rates data."""
        resp = gateway_call(
            bob_token, "bloomberg", "get_ref_data",
            {"tickers": ["AAPL"], "fields": ["PX_LAST"], "desk": "rates"},
        )
        assert resp.status_code == 200

    def test_bob_equities_denied(self, bob_token: str):
        """Bob (rates desk) CANNOT access equities desk data."""
        resp = gateway_call(
            bob_token, "bloomberg", "get_ref_data",
            {"tickers": ["AAPL"], "fields": ["PX_LAST"], "desk": "equities"},
        )
        body = resp.json()
        if resp.status_code == 200:
            assert "error" in body, "Expected PM isolation denial for equities desk"
        else:
            assert resp.status_code in (403, 500)

    def test_charlie_multi_desk_equities(self, charlie_token: str):
        """Charlie (equities+vol desk) CAN access equities data."""
        resp = gateway_call(
            charlie_token, "bloomberg", "get_ref_data",
            {"tickers": ["AAPL"], "fields": ["PX_LAST"], "desk": "equities"},
        )
        assert resp.status_code == 200

    def test_charlie_multi_desk_vol(self, charlie_token: str):
        """Charlie (equities+vol desk) CAN access vol data."""
        resp = gateway_call(
            charlie_token, "bloomberg", "get_ref_data",
            {"tickers": ["SPX"], "fields": ["IMPLIED_VOL_30D"], "desk": "vol"},
        )
        assert resp.status_code == 200

    def test_charlie_multi_desk_rates_denied(self, charlie_token: str):
        """Charlie (equities+vol desk) CANNOT access rates desk data."""
        resp = gateway_call(
            charlie_token, "bloomberg", "get_ref_data",
            {"tickers": ["AAPL"], "fields": ["PX_LAST"], "desk": "rates"},
        )
        body = resp.json()
        if resp.status_code == 200:
            assert "error" in body, "Expected PM isolation denial for rates desk"
        else:
            assert resp.status_code in (403, 500)

    def test_risk_isolation_alice_equities(self, alice_token: str):
        """PM isolation is enforced on Risk MCP too — not just Bloomberg."""
        resp = gateway_call(
            alice_token, "risk", "calculate_var",
            {"desk": "equities", "metric": "var", "confidence": 0.99, "horizon_days": 1},
        )
        assert resp.status_code == 200

    def test_risk_isolation_alice_rates_denied(self, alice_token: str):
        """Alice cannot access rates desk VaR."""
        resp = gateway_call(
            alice_token, "risk", "calculate_var",
            {"desk": "rates", "metric": "var", "confidence": 0.99, "horizon_days": 1},
        )
        body = resp.json()
        if resp.status_code == 200:
            assert "error" in body
        else:
            assert resp.status_code in (403, 500)
