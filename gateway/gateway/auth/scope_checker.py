"""Pre-exchange scope validation. Fails fast before Keycloak round-trip."""

from __future__ import annotations

import logging

from fastapi import HTTPException

logger = logging.getLogger(__name__)


def check_scope(claims: dict, required_scope: str) -> None:
    """
    Verify the JWT contains the required scope for the target route.

    Runs BEFORE token exchange — if the caller lacks the scope,
    we return 403 immediately without a Keycloak round-trip.

    Args:
        claims: Decoded JWT claims dict.
        required_scope: The scope string required by the route (e.g. 'bloomberg:read').

    Raises:
        HTTPException(403) if the required scope is missing.
    """
    token_scopes = set(claims.get("scope", "").split())

    # Also check realm_access.roles for Keycloak role-based scopes
    realm_roles = set(claims.get("realm_access", {}).get("roles", []))

    # Also check resource_access for client-specific roles
    client_roles: set[str] = set()
    for client_data in claims.get("resource_access", {}).values():
        client_roles.update(client_data.get("roles", []))

    all_permissions = token_scopes | realm_roles | client_roles

    if required_scope not in all_permissions:
        logger.warning(
            "Scope check FAILED: required=%s, token_scopes=%s, realm_roles=%s",
            required_scope,
            token_scopes,
            realm_roles,
        )
        raise HTTPException(
            status_code=403,
            detail=f"Missing required scope: {required_scope}. "
            f"Token scopes: {sorted(token_scopes)}",
        )
