"""Unit tests for scope checking."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from gateway.auth.scope_checker import check_scope


class TestScopeChecker:
    def test_scope_present_passes(self):
        claims = {"scope": "bloomberg:read risk:read"}
        check_scope(claims, "bloomberg:read")  # Should not raise

    def test_scope_missing_raises_403(self):
        claims = {"scope": "bloomberg:read"}
        with pytest.raises(HTTPException) as exc_info:
            check_scope(claims, "risk:read")
        assert exc_info.value.status_code == 403

    def test_realm_roles_checked(self):
        claims = {
            "scope": "",
            "realm_access": {"roles": ["bloomberg:read", "risk:read"]},
        }
        check_scope(claims, "bloomberg:read")  # Should not raise

    def test_client_roles_checked(self):
        claims = {
            "scope": "",
            "resource_access": {
                "mcp-gateway": {"roles": ["bloomberg:read"]}
            },
        }
        check_scope(claims, "bloomberg:read")  # Should not raise

    def test_empty_claims_raises_403(self):
        claims = {}
        with pytest.raises(HTTPException) as exc_info:
            check_scope(claims, "bloomberg:read")
        assert exc_info.value.status_code == 403
