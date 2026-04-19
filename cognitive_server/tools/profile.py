"""
get_pm_profile tool implementation.

Builds a full CognitiveProfile for a PM by combining:
- Raw interaction statistics from TimescaleDB
- Pattern analysis (frequency + sequential)
- The latest converged HeuristicModel from the ECEF engine

Returns a structured CognitiveProfile that surfaces decision patterns,
peak activity hours, primary tools, and the underlying heuristic model.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Optional

import structlog

from cognitive_server.db.connection import acquire
from cognitive_server.ecef.equilibrium import ECEFEngine
from cognitive_server.ecef.models import CognitiveProfile, HeuristicModel
from cognitive_server.patterns.extractor import PatternExtractor

log = structlog.get_logger("cognitive.tools.profile")

_engine = ECEFEngine()
_extractor = PatternExtractor()

_INTERACTIONS_SQL = """
SELECT session_id, pm_sub, tool_name, tool_server, arguments,
       result_summary, preceding_tool, preceding_interval_ms,
       timestamp, pm_desk, latency_ms
FROM pm_interactions
WHERE pm_sub = $1
ORDER BY timestamp ASC
"""

_OTHER_PM_SQL = """
SELECT session_id, pm_sub, tool_name, tool_server, arguments,
       result_summary, preceding_tool, preceding_interval_ms,
       timestamp, pm_desk, latency_ms
FROM pm_interactions
WHERE pm_sub != $1
ORDER BY timestamp ASC
"""


def _compute_avg_session_length(interactions: list[dict[str, Any]]) -> float:
    """Return average number of tool calls per session."""
    if not interactions:
        return 0.0
    sessions: dict[str, int] = defaultdict(int)
    for row in interactions:
        sessions[row.get("session_id", "_")] += 1
    return sum(sessions.values()) / len(sessions)


def _compute_peak_hours(interactions: list[dict[str, Any]], top_n: int = 3) -> list[int]:
    """Return the top-N UTC hours with the highest tool-call activity."""
    hour_counts: Counter[int] = Counter()
    for row in interactions:
        ts = row.get("timestamp")
        if isinstance(ts, datetime):
            hour_counts[ts.hour] += 1
        elif isinstance(ts, str):
            try:
                hour_counts[datetime.fromisoformat(ts).hour] += 1
            except ValueError:
                pass
    return [h for h, _ in hour_counts.most_common(top_n)]


def _derive_decision_patterns(
    analysis_chains: list,
    model: Optional[HeuristicModel],
) -> list[str]:
    """
    Produce human-readable descriptions of the PM's top decision patterns.

    Combines:
    - Top sequential chains (most frequent tool sequences)
    - Named trigger patterns from the heuristic model
    """
    patterns: list[str] = []

    # Top 3 sequential chains
    for chain_rec in analysis_chains[:3]:
        chain_str = " → ".join(chain_rec.chain)
        patterns.append(
            f"Sequence '{chain_str}' observed {chain_rec.frequency}× "
            f"(avg {round(chain_rec.avg_duration_ms or 0, 0):.0f} ms)"
        )

    # Named triggers from heuristic model
    if model:
        for trigger in model.triggers[:3]:
            seq_str = " → ".join(trigger.expected_sequence)
            patterns.append(
                f"Trigger '{trigger.trigger_condition}' → {seq_str} "
                f"({trigger.observed_frequency}× observed)"
            )

    return patterns if patterns else ["Insufficient data to derive patterns."]


async def get_pm_profile(pm_sub: str) -> dict[str, Any]:
    """
    Build and return a full CognitiveProfile for ``pm_sub``.

    Fetches all interaction history from TimescaleDB, runs pattern extraction,
    loads (or builds) the latest ECEF heuristic model, then assembles a
    :class:`CognitiveProfile`.

    Args:
        pm_sub: JWT ``sub`` claim identifying the PM.

    Returns:
        JSON-serialisable dict representation of :class:`CognitiveProfile`.
    """
    log.info("get_pm_profile_start", pm_sub=pm_sub)

    async with acquire() as conn:
        rows = await conn.fetch(_INTERACTIONS_SQL, pm_sub)
    interactions = [dict(r) for r in rows]

    if not interactions:
        profile = CognitiveProfile(
            pm_sub=pm_sub,
            total_interactions=0,
            primary_tools=[],
            decision_patterns=["No interaction history found."],
            avg_session_length=0.0,
            peak_hours=[],
            heuristic=None,
        )
        return profile.model_dump()

    # Pattern analysis
    analysis = _extractor.extract(interactions, pm_sub=pm_sub)

    # ECEF model (loads from DB or builds if absent)
    model = await _engine.get_or_build_model(pm_sub)

    avg_session = _compute_avg_session_length(interactions)
    peak_hours = _compute_peak_hours(interactions)
    decision_patterns = _derive_decision_patterns(analysis.chains, model)

    profile = CognitiveProfile(
        pm_sub=pm_sub,
        total_interactions=len(interactions),
        primary_tools=analysis.frequency.primary_tools,
        decision_patterns=decision_patterns,
        avg_session_length=round(avg_session, 2),
        peak_hours=peak_hours,
        heuristic=model,
    )

    log.info(
        "get_pm_profile_complete",
        pm_sub=pm_sub,
        total_interactions=len(interactions),
        primary_tools=analysis.frequency.primary_tools[:3],
    )
    return profile.model_dump()


async def compare_pm_patterns(pm_sub: str, other_pm: str) -> dict[str, Any]:
    """
    Compare the cognitive patterns of two PMs.

    Loads interaction history for both PMs, runs pattern extraction for each,
    and returns a side-by-side comparison of their primary tools, peak hours,
    and top sequential chains.

    Args:
        pm_sub:   The requesting PM's ``sub`` claim.
        other_pm: The ``sub`` claim of the PM to compare against.

    Returns:
        Dict with ``subject``, ``other``, and ``comparison`` keys.
    """
    log.info("compare_pm_patterns", subject=pm_sub, other=other_pm)

    async with acquire() as conn:
        rows_self = await conn.fetch(_INTERACTIONS_SQL, pm_sub)
        rows_other = await conn.fetch(_INTERACTIONS_SQL, other_pm)

    interactions_self = [dict(r) for r in rows_self]
    interactions_other = [dict(r) for r in rows_other]

    analysis_self = _extractor.extract(interactions_self, pm_sub=pm_sub)
    analysis_other = _extractor.extract(interactions_other, pm_sub=other_pm)

    def _summarise(analysis: Any, pm: str) -> dict[str, Any]:
        return {
            "pm_sub": pm,
            "total_interactions": analysis.raw_count,
            "primary_tools": analysis.frequency.primary_tools,
            "peak_hours": _compute_peak_hours(
                interactions_self if pm == pm_sub else interactions_other
            ),
            "top_chains": [
                {
                    "chain": list(cr.chain),
                    "frequency": cr.frequency,
                }
                for cr in analysis.chains[:5]
            ],
        }

    subject_summary = _summarise(analysis_self, pm_sub)
    other_summary = _summarise(analysis_other, other_pm)

    # Overlap: tools used by both
    shared_tools = list(
        set(subject_summary["primary_tools"]) & set(other_summary["primary_tools"])
    )

    return {
        "subject": subject_summary,
        "other": other_summary,
        "comparison": {
            "shared_primary_tools": shared_tools,
            "subject_unique_tools": list(
                set(subject_summary["primary_tools"]) - set(other_summary["primary_tools"])
            ),
            "other_unique_tools": list(
                set(other_summary["primary_tools"]) - set(subject_summary["primary_tools"])
            ),
        },
    }
