"""
Cognitive MCP Server.

Exposes five MCP tools that surface PM behavioural patterns learned via the
Evaluator-Constructor Equilibrium Framework (ECEF):

  - suggest_next_action   : predict the PM's next most-likely tool call
  - get_pm_profile        : full cognitive profile for the authenticated PM
  - get_interaction_history: raw interaction log for a configurable window
  - get_pattern_analysis  : current pattern extraction results
  - compare_pm_patterns   : side-by-side comparison of two PMs' behaviours

Authentication: BearerAuthProvider validates Keycloak-issued JWTs.
Port: 8013

Ingestion endpoint (fire-and-forget from gateway middleware):
  POST /ingest   — handled by cognitive_server.ingest.interaction_logger

Entrypoint:
    python -m cognitive_server.server
"""

from __future__ import annotations

import os
import sys

# Allow sibling imports when run as __main__ from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from mcp.server.fastmcp import Context, FastMCP

from cognitive_server.db.connection import acquire, close_pool
from cognitive_server.ecef.equilibrium import ECEFEngine
from cognitive_server.ingest.interaction_logger import router as ingest_router
from cognitive_server.patterns.extractor import PatternExtractor
from cognitive_server.tools.profile import compare_pm_patterns as _compare_pm_patterns
from cognitive_server.tools.profile import get_pm_profile as _get_pm_profile
from cognitive_server.tools.suggest import suggest_next_action as _suggest_next_action

log = structlog.get_logger("cognitive.server")

# ---------------------------------------------------------------------------
# Server + auth setup
# ---------------------------------------------------------------------------

try:
    from servers.shared.auth import make_bearer_auth  # type: ignore[import]
    _auth = make_bearer_auth("cognitive-mcp", ["cognitive:read"])
except Exception:
    # Running standalone without the shared servers package on the path —
    # auth is disabled (e.g. local development / unit tests).
    log.warning("auth_disabled_shared_package_not_found")
    _auth = None

mcp = FastMCP(
    name="cognitive-mcp",
    auth=_auth,
)

# Mount the FastAPI ingestion router so the same process handles both the MCP
# streamable-HTTP transport and the fire-and-forget POST /ingest endpoint.
# FastMCP exposes an underlying Starlette/FastAPI app via ``mcp.app``.
try:
    mcp.app.include_router(ingest_router)  # type: ignore[attr-defined]
    log.info("ingest_router_mounted", prefix="/ingest")
except AttributeError:
    log.warning(
        "ingest_router_not_mounted",
        reason="FastMCP version does not expose .app — ingestion endpoint unavailable",
    )

_engine = ECEFEngine()
_extractor = PatternExtractor()

# ---------------------------------------------------------------------------
# Tool registrations
# ---------------------------------------------------------------------------

_INTERACTIONS_SQL = """
SELECT session_id, pm_sub, tool_name, tool_server,
       preceding_tool, preceding_interval_ms, timestamp, pm_desk
FROM pm_interactions
WHERE pm_sub = $1
  AND timestamp >= NOW() - ($2 * INTERVAL '1 hour')
ORDER BY timestamp DESC
LIMIT 1000
"""


@mcp.tool()
async def suggest_next_action(
    context: str,
    desk: str,
    ctx: Context,
    current_tool: Optional[str] = None,
) -> dict[str, Any]:
    """
    Predict the PM's next most-likely tool call based on their learned behaviour.

    Uses the ECEF-converged Markov transition model to look up the top-3
    most probable follow-on tools given the current tool (or session start).

    USE THIS FOR:
      - Proactive workflow suggestions ("you usually run calculate_risk next")
      - Session-start bootstrapping (no current_tool)
      - Reducing cognitive load during complex multi-tool workflows

    DO NOT USE FOR:
      - Fetching market data or positions — use bloomberg-mcp / risk-mcp
      - Authoritative recommendations — suggestions are probabilistic

    Args:
        context:      Free-text description of what you are currently doing.
        desk:         Your trading desk identifier (from JWT claims).
        ctx:          MCP context carrying JWT auth claims.
        current_tool: The most recently executed tool name, or omit at session start.
    """
    pm_sub = _extract_pm_sub(ctx)
    return await _suggest_next_action(
        pm_sub=pm_sub,
        context=context,
        current_tool=current_tool,
        desk=desk,
    )


@mcp.tool()
async def get_pm_profile(
    ctx: Context,
    pm_sub: Optional[str] = None,
) -> dict[str, Any]:
    """
    Return the full cognitive profile for a PM.

    Combines interaction statistics, pattern analysis, and the ECEF heuristic
    model into a single structured profile.  By default returns the profile of
    the authenticated PM; admins may supply a different ``pm_sub``.

    USE THIS FOR:
      - Understanding a PM's typical tool-usage patterns
      - Reviewing convergence quality of the ECEF model
      - Onboarding analysis (new PMs vs. experienced patterns)

    DO NOT USE FOR:
      - Real-time position or risk data — use risk-mcp
      - Compliance or audit purposes — use dedicated audit tools

    Args:
        ctx:    MCP context carrying JWT auth claims.
        pm_sub: Override subject — defaults to the authenticated PM.
    """
    target = pm_sub or _extract_pm_sub(ctx)
    return await _get_pm_profile(target)


@mcp.tool()
async def get_interaction_history(
    ctx: Context,
    window_hours: int = 24,
) -> dict[str, Any]:
    """
    Return raw interaction history for the authenticated PM.

    Fetches up to 1000 recent tool-call events within the specified window.
    Useful for debugging, self-reflection, and workflow review.

    USE THIS FOR:
      - Reviewing your recent tool-usage activity
      - Debugging unexpected ECEF suggestions
      - Session replay and workflow audits

    DO NOT USE FOR:
      - Aggregated pattern analysis — use get_pattern_analysis
      - Cross-PM comparisons — use compare_pm_patterns

    Args:
        ctx:          MCP context carrying JWT auth claims.
        window_hours: Look-back window in hours (default 24, max 168).
    """
    if window_hours < 1 or window_hours > 168:
        return {"error": "window_hours must be between 1 and 168"}

    pm_sub = _extract_pm_sub(ctx)

    async with acquire() as conn:
        rows = await conn.fetch(_INTERACTIONS_SQL, pm_sub, window_hours)

    history = [
        {
            "tool_name": r["tool_name"],
            "tool_server": r["tool_server"],
            "preceding_tool": r["preceding_tool"],
            "preceding_interval_ms": r["preceding_interval_ms"],
            "session_id": r["session_id"],
            "desk": r["pm_desk"],
            "timestamp": r["timestamp"].isoformat() if isinstance(r["timestamp"], datetime) else r["timestamp"],
        }
        for r in rows
    ]

    return {
        "pm_sub": pm_sub,
        "window_hours": window_hours,
        "count": len(history),
        "interactions": history,
    }


@mcp.tool()
async def get_pattern_analysis(ctx: Context) -> dict[str, Any]:
    """
    Return current pattern extraction results for the authenticated PM.

    Runs the PatternExtractor over all available interaction history and
    returns frequency statistics, sequential chains, and ECEF model summary.

    USE THIS FOR:
      - Exploring which tools you use most and when
      - Understanding sequential decision chains
      - Reviewing ECEF model quality and trigger patterns

    DO NOT USE FOR:
      - Real-time next-action suggestions — use suggest_next_action
      - Full profile with session stats — use get_pm_profile

    Args:
        ctx: MCP context carrying JWT auth claims.
    """
    pm_sub = _extract_pm_sub(ctx)

    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT session_id, pm_sub, tool_name, tool_server, "
            "preceding_tool, preceding_interval_ms, timestamp, pm_desk, latency_ms "
            "FROM pm_interactions WHERE pm_sub = $1 ORDER BY timestamp ASC",
            pm_sub,
        )
    interactions = [dict(r) for r in rows]

    analysis = _extractor.extract(interactions, pm_sub=pm_sub)
    model = await _engine.get_or_build_model(pm_sub)

    return {
        "pm_sub": pm_sub,
        "total_interactions": analysis.raw_count,
        "session_count": analysis.session_count,
        "primary_tools": analysis.frequency.primary_tools,
        "tool_call_counts": analysis.frequency.tool_call_counts,
        "time_of_day_distribution": analysis.frequency.time_of_day_dist,
        "desk_distribution": analysis.frequency.desk_dist,
        "top_chains": [
            {
                "chain": list(cr.chain),
                "frequency": cr.frequency,
                "avg_duration_ms": cr.avg_duration_ms,
            }
            for cr in analysis.chains[:10]
        ],
        "model_summary": {
            "version": model.version,
            "confidence": round(model.confidence, 4),
            "convergence_gap": round(model.convergence_gap, 6),
            "iteration_count": model.iteration_count,
            "n_transitions": len(model.transitions),
            "n_triggers": len(model.triggers),
        },
    }


@mcp.tool()
async def compare_pm_patterns(other_pm: str, ctx: Context) -> dict[str, Any]:
    """
    Compare your cognitive patterns with another PM.

    Returns a side-by-side breakdown of primary tools, peak hours, top
    sequential chains, and unique vs. shared tool preferences.

    USE THIS FOR:
      - Mentorship: senior PM sharing patterns with junior PM
      - Desk-level pattern benchmarking
      - Identifying workflow divergence between PMs on the same desk

    DO NOT USE FOR:
      - Compliance monitoring — use dedicated audit tooling
      - Performance evaluation — patterns are descriptive, not prescriptive

    Args:
        other_pm: JWT ``sub`` of the PM to compare against.
        ctx:      MCP context carrying JWT auth claims.
    """
    pm_sub = _extract_pm_sub(ctx)
    return await _compare_pm_patterns(pm_sub=pm_sub, other_pm=other_pm)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_pm_sub(ctx: Context) -> str:
    """Extract the ``sub`` claim from the JWT in the MCP context.

    Falls back to ``"anonymous"`` when running without auth (local dev).
    """
    try:
        claims = ctx.auth_context  # type: ignore[attr-defined]
        if claims and hasattr(claims, "sub"):
            return claims.sub
        if isinstance(claims, dict):
            return claims.get("sub", "anonymous")
    except (AttributeError, TypeError):
        pass
    return "anonymous"


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    log.info("cognitive_mcp_starting", host="0.0.0.0", port=8013, path="/mcp")
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8013,
        path="/mcp",
    )


if __name__ == "__main__":
    main()
