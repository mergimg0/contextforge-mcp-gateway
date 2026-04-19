"""
Plan Executor — executes a ValidationPlan against the MCP gateway.

Execution model:
  - Groups are processed sequentially in dependency order.
  - Within each group, all ToolCallSpecs are dispatched concurrently
    via asyncio.gather.
  - Non-required calls that fail are recorded as failed results but do
    not abort the group or the plan.
  - Required calls that fail raise PlanExecutionError unless partial
    failure handling allows continuation.
"""

from __future__ import annotations

import asyncio
import time
from typing import Sequence

import structlog

from ..planner.models import ToolCallGroup, ToolCallSpec, ValidationPlan
from .gateway_client import GatewayClient, GatewayError
from .models import ToolCallResult

log = structlog.get_logger("orchestrator.executor")


class PlanExecutionError(Exception):
    """Raised when a required tool call fails and the plan cannot continue."""


async def execute_plan(
    plan: ValidationPlan,
    client: GatewayClient,
    *,
    allow_partial_failure: bool = True,
) -> list[ToolCallResult]:
    """
    Execute all groups in a ValidationPlan, returning every ToolCallResult.

    Args:
        plan:                  The validated plan to execute.
        client:                Authenticated GatewayClient (must be open).
        allow_partial_failure: When True, required-call failures are logged
                               but do not abort the plan.  When False, the
                               first required-call failure raises
                               PlanExecutionError.

    Returns:
        Flat list of ToolCallResult in execution order (group by group,
        parallel calls within each group sorted by server+tool name).
    """
    all_results: list[ToolCallResult] = []
    completed_groups: set[str] = set()

    # Build a simple dependency-ordered queue.
    # Groups whose deps are all satisfied get executed next.
    remaining = list(plan.groups)

    while remaining:
        # Find all groups whose dependencies are fully satisfied
        ready = [
            g for g in remaining
            if all(dep in completed_groups for dep in g.dependencies)
        ]

        if not ready:
            unsatisfied = [g.name for g in remaining]
            raise PlanExecutionError(
                f"Dependency deadlock: groups {unsatisfied} have unsatisfied deps "
                f"but none of their dependencies are in remaining groups. "
                f"Completed: {sorted(completed_groups)}"
            )

        # Execute all ready groups; if multiple are ready and have no deps on
        # each other, run them in parallel too.
        group_results = await asyncio.gather(
            *[_execute_group(g, client, allow_partial_failure) for g in ready],
            return_exceptions=False,
        )

        for group, results in zip(ready, group_results):
            all_results.extend(results)
            completed_groups.add(group.name)
            remaining.remove(group)

    log.info(
        "plan_executed",
        total_calls=len(all_results),
        successful=sum(1 for r in all_results if r.success),
        failed=sum(1 for r in all_results if not r.success),
    )

    return all_results


async def _execute_group(
    group: ToolCallGroup,
    client: GatewayClient,
    allow_partial_failure: bool,
) -> list[ToolCallResult]:
    """Execute all calls in a group concurrently and return their results."""
    log.debug("executing_group", group=group.name, calls=len(group.calls))

    tasks = [_execute_call(call, client) for call in group.calls]
    results: list[ToolCallResult] = await asyncio.gather(*tasks, return_exceptions=False)

    # Check for required failures
    for result in results:
        if not result.success and result.call.required and not allow_partial_failure:
            raise PlanExecutionError(
                f"Required call {result.call.server}/{result.call.tool} failed: "
                f"{result.error}"
            )

    return list(results)


async def _execute_call(call: ToolCallSpec, client: GatewayClient) -> ToolCallResult:
    """Execute a single ToolCallSpec and return a ToolCallResult."""
    start = time.monotonic()
    try:
        data = await client.call_tool(
            server=call.server,
            tool=call.tool,
            arguments=call.arguments,
        )
        latency_ms = (time.monotonic() - start) * 1000
        log.debug(
            "tool_call_success",
            server=call.server,
            tool=call.tool,
            latency_ms=round(latency_ms, 1),
        )
        return ToolCallResult(
            call=call,
            success=True,
            data=data,
            latency_ms=latency_ms,
        )
    except GatewayError as exc:
        latency_ms = (time.monotonic() - start) * 1000
        log.warning(
            "tool_call_failed",
            server=call.server,
            tool=call.tool,
            error=str(exc),
            status_code=exc.status_code,
            required=call.required,
            latency_ms=round(latency_ms, 1),
        )
        return ToolCallResult(
            call=call,
            success=False,
            error=str(exc),
            latency_ms=latency_ms,
            status_code=exc.status_code,
        )
    except Exception as exc:
        latency_ms = (time.monotonic() - start) * 1000
        log.error(
            "tool_call_unexpected_error",
            server=call.server,
            tool=call.tool,
            error=str(exc),
            latency_ms=round(latency_ms, 1),
        )
        return ToolCallResult(
            call=call,
            success=False,
            error=f"Unexpected error: {exc}",
            latency_ms=latency_ms,
        )
