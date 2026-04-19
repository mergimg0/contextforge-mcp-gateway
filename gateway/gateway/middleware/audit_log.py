"""Structured JSON audit logging for compliance."""

from __future__ import annotations

import time
import logging

import structlog

audit_logger = structlog.get_logger("mcp.audit")
logger = logging.getLogger(__name__)


def log_access_decision(
    *,
    request_id: str,
    caller_sub: str,
    route_name: str,
    tool_name: str | None = None,
    scope_check: str = "PASS",
    exchange_performed: bool = False,
    exchange_audience: str | None = None,
    exchange_cached: bool = False,
    backend_status: int | None = None,
    latency_ms: float | None = None,
    decision: str = "PERMIT",
    detail: str | None = None,
) -> None:
    """Emit a structured audit log entry for every gateway request."""
    audit_logger.info(
        "mcp_gateway_access",
        request_id=request_id,
        caller_sub=caller_sub,
        route=route_name,
        tool=tool_name,
        scope_check=scope_check,
        exchange_performed=exchange_performed,
        exchange_audience=exchange_audience,
        exchange_cached=exchange_cached,
        backend_status=backend_status,
        latency_ms=round(latency_ms, 2) if latency_ms else None,
        decision=decision,
        detail=detail,
    )
