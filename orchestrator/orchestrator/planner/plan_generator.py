"""
Plan Generator — maps a ThesisStatement to a ValidationPlan.

Selects the appropriate template for the thesis claim_type, substitutes
date placeholders with real ISO-8601 dates, and assembles the final plan.
"""

from __future__ import annotations

from datetime import date, timedelta

import structlog

from ..parser.models import ThesisStatement
from .models import ToolCallGroup, ToolCallSpec, ValidationPlan
from .plan_templates import TEMPLATES

log = structlog.get_logger("orchestrator.planner")

# Latency estimates per server (ms), used for plan estimation
_SERVER_LATENCY_MS = {
    "bloomberg": 150,
    "risk": 200,
    "research": 120,
}

# Default latency when server is unknown
_DEFAULT_LATENCY_MS = 200


def generate_plan(thesis: ThesisStatement, desk: str) -> ValidationPlan:
    """
    Generate a ValidationPlan for the given thesis.

    Selects a template by claim_type, substitutes asset and desk into tool
    arguments, and resolves date placeholders to concrete ISO-8601 strings.

    Args:
        thesis: Parsed thesis statement from the parser layer.
        desk:   Trading desk identifier (e.g. "vol", "equities").

    Returns:
        ValidationPlan ready for execution by PlanExecutor.
    """
    claim_type = thesis.claim_type
    template_fn = TEMPLATES.get(claim_type)

    if template_fn is None:
        log.warning("no_template_for_claim_type", claim_type=claim_type.value)
        # Fallback: use relative_value template as a generic baseline
        from .plan_templates import relative_value_template
        template_fn = relative_value_template

    asset = thesis.asset if thesis.asset != "UNKNOWN" else "SPX"
    groups = template_fn(asset=asset, desk=desk)

    # Substitute date placeholders
    today = date.today()
    groups = _substitute_dates(groups, today)

    total_calls = sum(len(g.calls) for g in groups)
    estimated_latency = _estimate_latency_ms(groups)

    rationale = _build_rationale(thesis, desk)

    log.info(
        "plan_generated",
        claim_type=claim_type.value,
        asset=asset,
        desk=desk,
        groups=len(groups),
        total_calls=total_calls,
        estimated_latency_ms=estimated_latency,
    )

    return ValidationPlan(
        thesis=thesis,
        groups=groups,
        estimated_calls=total_calls,
        estimated_latency_ms=estimated_latency,
        plan_rationale=rationale,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _substitute_dates(groups: list[ToolCallGroup], today: date) -> list[ToolCallGroup]:
    """
    Replace date placeholder strings in tool arguments with real ISO-8601 dates.

    Supported placeholders:
      {{date_today}}      → today's date
      {{date_minus_90d}}  → 90 days ago
      {{date_minus_252d}} → 252 trading days ago (approx 1 year)
    """
    replacements = {
        "{{date_today}}": today.isoformat(),
        "{{date_minus_90d}}": (today - timedelta(days=90)).isoformat(),
        "{{date_minus_252d}}": (today - timedelta(days=365)).isoformat(),
        "{{date_minus_30d}}": (today - timedelta(days=30)).isoformat(),
        "{{date_minus_180d}}": (today - timedelta(days=180)).isoformat(),
    }

    resolved_groups: list[ToolCallGroup] = []
    for group in groups:
        resolved_calls: list[ToolCallSpec] = []
        for call in group.calls:
            new_args = _deep_replace(call.arguments, replacements)
            resolved_calls.append(call.model_copy(update={"arguments": new_args}))
        resolved_groups.append(group.model_copy(update={"calls": resolved_calls}))

    return resolved_groups


def _deep_replace(obj: object, replacements: dict[str, str]) -> object:
    """Recursively walk a JSON-like structure and replace placeholder strings."""
    if isinstance(obj, str):
        for placeholder, value in replacements.items():
            obj = obj.replace(placeholder, value)
        return obj
    if isinstance(obj, dict):
        return {k: _deep_replace(v, replacements) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_replace(item, replacements) for item in obj]
    return obj


def _estimate_latency_ms(groups: list[ToolCallGroup]) -> int:
    """
    Estimate total wall-clock latency assuming parallel execution within groups
    and sequential execution between groups.

    Returns the sum of (max latency of each group's calls).
    """
    total = 0
    for group in groups:
        if not group.calls:
            continue
        group_max = max(
            _SERVER_LATENCY_MS.get(call.server, _DEFAULT_LATENCY_MS)
            for call in group.calls
        )
        total += group_max
    return total


def _build_rationale(thesis: ThesisStatement, desk: str) -> str:
    """Generate a one-sentence rationale explaining the validation strategy."""
    return (
        f"Validate {thesis.claim_type.value.replace('_', '-')} thesis on {thesis.asset} "
        f"for {desk} desk by gathering market data, stress-testing risk dimensions, "
        f"and synthesising analyst research into a scored evidence report."
    )
