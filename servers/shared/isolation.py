"""PM Isolation middleware — shared across all MCP backend servers."""

from __future__ import annotations

import logging
from typing import Literal, Optional

import structlog

audit_log = structlog.get_logger("mcp.audit")
logger = logging.getLogger(__name__)

DeskId = Literal["equities", "rates", "vol", "macro", "credit"]

TRUSTED_ACTORS = {"mcp-gateway"}


class DeskIsolation:
    """
    Reusable PM isolation logic for MCP tool functions.

    Extracts caller identity from JWT claims, validates desk access,
    validates the delegation chain (act claim), and emits audit logs.
    """

    @staticmethod
    def enforce(ctx, desk: str, tool_name: str) -> tuple[str, list[str]]:
        """
        Validate PM has access to the requested desk.

        Returns (subject, desk_access) on success.
        Raises McpError(PERMISSION_DENIED) on failure.
        Always logs the access decision.
        """
        from mcp import McpError
        from mcp.types import ErrorCode

        claims = ctx.auth or {}
        subject = claims.get("sub", "unknown")
        desk_access = claims.get("desk_access", [])
        if isinstance(desk_access, str):
            desk_access = [desk_access]

        # Validate delegation chain
        act_claim = claims.get("act")
        actor = act_claim.get("sub") if act_claim else None
        if actor and actor not in TRUSTED_ACTORS:
            audit_log.warning(
                "untrusted_actor",
                subject=subject,
                actor=actor,
                tool=tool_name,
            )
            raise McpError(ErrorCode.PERMISSION_DENIED, f"Untrusted actor: {actor}")

        # Validate desk access
        permitted = desk in desk_access

        audit_log.info(
            "mcp_access_decision",
            tool=tool_name,
            subject=subject,
            actor=actor,
            desk_requested=desk,
            desk_access=desk_access,
            decision="PERMIT" if permitted else "DENY",
        )

        if not permitted:
            raise McpError(
                ErrorCode.PERMISSION_DENIED,
                f"Caller '{subject}' does not have access to desk '{desk}'. "
                f"Authorized desks: {desk_access}",
            )

        return subject, desk_access

    @staticmethod
    def get_caller_context(ctx) -> tuple[str, list[str], Optional[str]]:
        """Extract caller identity without enforcement."""
        claims = ctx.auth or {}
        subject = claims.get("sub", "unknown")
        desk_access = claims.get("desk_access", [])
        if isinstance(desk_access, str):
            desk_access = [desk_access]
        actor = claims.get("act", {}).get("sub")
        return subject, desk_access, actor
