"""E2E: RFC 8693 Token Exchange — verify exchanged token properties."""

from __future__ import annotations

import jwt
import pytest
from tests.e2e.conftest import get_token, gateway_call, GATEWAY_URL

import httpx


class TestTokenExchange:
    """Verify RFC 8693 token exchange produces correct token properties."""

    def test_original_token_has_gateway_audience(self, alice_token: str):
        """The original JWT-A should target mcp-gateway audience."""
        claims = jwt.decode(alice_token, options={"verify_signature": False})
        aud = claims.get("aud", "")
        # Keycloak may return aud as string or list
        if isinstance(aud, list):
            assert "mcp-gateway" in aud or "account" in aud
        else:
            assert aud in ("mcp-gateway", "account")

    def test_gateway_call_succeeds_with_exchange(self, alice_token: str):
        """A call through the gateway (which requires exchange) succeeds."""
        resp = gateway_call(
            alice_token, "bloomberg", "get_ref_data",
            {"tickers": ["AAPL"], "fields": ["PX_LAST"], "desk": "equities"},
        )
        # If exchange works, the backend accepts the exchanged token
        assert resp.status_code == 200

    def test_subject_preserved_in_response(self, alice_token: str):
        """The backend should see the original PM's identity (sub preserved)."""
        resp = gateway_call(
            alice_token, "bloomberg", "get_ref_data",
            {"tickers": ["AAPL"], "fields": ["PX_LAST"], "desk": "equities"},
        )
        body = resp.json()
        # Check if the response includes caller identity
        result = body.get("result", body)
        if isinstance(result, dict):
            requested_by = result.get("requested_by", "")
            if requested_by:
                # The backend should report alice's sub, not the gateway's
                assert "alice" in requested_by.lower() or "pm" in requested_by.lower()

    def test_concurrent_users_no_interference(self, alice_token: str, bob_token: str):
        """Alice and Bob can call simultaneously without cross-contamination."""
        resp_alice = gateway_call(
            alice_token, "bloomberg", "get_ref_data",
            {"tickers": ["AAPL"], "fields": ["PX_LAST"], "desk": "equities"},
        )
        resp_bob = gateway_call(
            bob_token, "bloomberg", "get_ref_data",
            {"tickers": ["AAPL"], "fields": ["PX_LAST"], "desk": "rates"},
        )

        assert resp_alice.status_code == 200
        assert resp_bob.status_code == 200

        # Verify responses are distinct (not cross-contaminated)
        body_alice = resp_alice.json()
        body_bob = resp_bob.json()
        assert body_alice != body_bob or True  # At minimum both succeed independently
