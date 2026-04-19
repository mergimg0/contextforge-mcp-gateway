"""
Pydantic models for the fire-and-forget interaction ingestion endpoint.

These mirror the ``pm_interactions`` TimescaleDB hypertable schema so that
incoming gateway events map cleanly to a single INSERT statement with no
further transformation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class InteractionEvent(BaseModel):
    """
    A single PM tool-call event forwarded by the gateway middleware.

    The gateway emits one of these for every tool invocation it proxies.
    Fields map 1-to-1 to columns in ``pm_interactions``.

    Attributes:
        pm_sub:               JWT ``sub`` claim — unique PM identifier.
        tool_name:            Name of the MCP tool that was called.
        tool_server:          MCP server that hosts the tool (e.g. ``bloomberg-mcp``).
        arguments:            Tool arguments as a free-form dict (stored as JSONB).
        result_summary:       Short text summary of the tool result (may be None for
                              failed calls).
        session_id:           Client-supplied session identifier for grouping related
                              calls into a workflow.
        preceding_tool:       Tool called immediately before this one in the session
                              (None if this is the first call).
        preceding_interval_ms: Wall-clock milliseconds between the preceding tool
                              completing and this call starting.
        timestamp:            UTC wall-clock time at which the gateway received the
                              call.  Defaults to ``datetime.utcnow()`` so callers may
                              omit it.
    """

    pm_sub: str = Field(..., description="JWT sub claim — unique PM identifier")
    tool_name: str = Field(..., description="Name of the MCP tool invoked")
    tool_server: str = Field(..., description="Hosting MCP server name")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Tool call arguments (stored as JSONB)",
    )
    result_summary: Optional[str] = Field(
        default=None,
        description="Short text summary of the tool result",
    )
    session_id: str = Field(..., description="Session grouping identifier")
    preceding_tool: Optional[str] = Field(
        default=None,
        description="Tool called immediately before this one in the session",
    )
    preceding_interval_ms: Optional[int] = Field(
        default=None,
        description="Milliseconds between preceding tool completion and this call",
        ge=0,
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp at which the gateway received the call",
    )
    desk: Optional[str] = Field(
        default=None,
        description="Trading desk identifier extracted from the JWT desk_access claim",
    )
