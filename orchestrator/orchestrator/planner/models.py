"""
Pydantic models for the validation plan layer.

A ValidationPlan describes the ordered set of MCP tool calls needed to
validate a thesis.  Calls are grouped into parallel batches (within a group)
with explicit dependency ordering between groups.
"""

from typing import Any, Optional

from pydantic import BaseModel, Field

from ..parser.models import ThesisStatement


class ToolCallSpec(BaseModel):
    """
    Specification for a single MCP tool call to be made through the gateway.

    `server` maps to the gateway route prefix (bloomberg / risk / research).
    `tool` is the MCP tool name on that backend.
    `arguments` are the JSON-serialisable arguments to pass.
    """

    server: str = Field(description="Gateway route: 'bloomberg', 'risk', or 'research'")
    tool: str = Field(description="MCP tool name on the target server")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool call arguments")
    purpose: str = Field(description="Human-readable explanation of why this call is needed")
    required: bool = Field(
        default=True,
        description="If False, failure of this call does not abort the plan",
    )
    # Cache key prefix for deduplication (optional — executor fills this in)
    cache_key: Optional[str] = Field(default=None, exclude=True)


class ToolCallGroup(BaseModel):
    """
    A named group of ToolCallSpecs that can be executed in parallel.

    Groups are executed in dependency order: a group will not start until all
    groups listed in `dependencies` have completed.
    """

    name: str = Field(description="Group identifier (e.g. 'market_data', 'risk_analysis')")
    calls: list[ToolCallSpec] = Field(description="Tool calls that run in parallel within this group")
    dependencies: list[str] = Field(
        default_factory=list,
        description="Names of groups that must complete before this group starts",
    )
    description: Optional[str] = Field(
        default=None, description="Human-readable summary of what this group collects"
    )


class ValidationPlan(BaseModel):
    """
    Complete ordered execution plan for validating a thesis.

    The executor walks `groups` in dependency order, running calls within
    each group concurrently via asyncio.gather.
    """

    thesis: ThesisStatement = Field(description="The parsed thesis this plan validates")
    groups: list[ToolCallGroup] = Field(description="Ordered call groups")
    estimated_calls: int = Field(description="Total number of MCP tool calls")
    estimated_latency_ms: int = Field(
        description="Rough latency estimate (ms) assuming parallel within-group execution"
    )
    plan_rationale: str = Field(
        default="",
        description="One-sentence explanation of the overall validation strategy",
    )
