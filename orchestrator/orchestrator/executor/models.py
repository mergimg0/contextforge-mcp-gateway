"""
Pydantic models for the executor layer.
"""

from typing import Any, Optional

from pydantic import BaseModel, Field

from ..planner.models import ToolCallSpec


class ToolCallResult(BaseModel):
    """
    Result of executing a single ToolCallSpec against the gateway.

    On success, `data` contains the parsed JSON response body.
    On failure, `error` contains a human-readable error message and
    `data` is None.
    """

    call: ToolCallSpec = Field(description="The spec that was executed")
    success: bool = Field(description="Whether the tool call completed without error")
    data: Optional[dict[str, Any]] = Field(
        default=None,
        description="Parsed response body on success",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message on failure",
    )
    latency_ms: float = Field(
        default=0.0,
        description="Round-trip latency in milliseconds",
    )
    status_code: Optional[int] = Field(
        default=None,
        description="HTTP status code from the gateway",
    )
