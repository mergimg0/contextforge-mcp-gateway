"""
Tool usage frequency analysis per PM.

Provides call-count, time-of-day, and desk distributions derived directly
from the ``pm_interactions`` TimescaleDB hypertable.  These statistics are
used both as standalone analytics and as features fed into the ECEF
constructor.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

log = structlog.get_logger("cognitive.patterns.frequency")


@dataclass
class FrequencyStats:
    """
    Aggregated frequency statistics for a single PM.

    Attributes:
        pm_sub:             PM identifier.
        tool_call_counts:   ``{tool_name: total_call_count}`` across all time.
        time_of_day_dist:   ``{tool_name: {hour_0_23: count}}`` — when each
                            tool is used throughout the day.
        desk_dist:          ``{tool_name: {desk_name: count}}`` — which desk
                            is active when each tool is called.
        total_calls:        Sum of all tool calls in the analysis window.
        primary_tools:      Up to five most-called tools, ordered by frequency.
    """

    pm_sub: str
    tool_call_counts: dict[str, int] = field(default_factory=dict)
    time_of_day_dist: dict[str, dict[int, int]] = field(default_factory=dict)
    desk_dist: dict[str, dict[str, int]] = field(default_factory=dict)
    total_calls: int = 0
    primary_tools: list[str] = field(default_factory=list)


def analyse_frequency(
    interactions: list[dict[str, Any]],
    pm_sub: str,
) -> FrequencyStats:
    """
    Compute frequency statistics from a list of raw interaction dicts.

    Each dict must contain at minimum:

    - ``tool_name`` (str)
    - ``timestamp`` (datetime or ISO-8601 str)

    Optional keys:

    - ``pm_desk`` (list[str] | None)

    Args:
        interactions: Rows fetched from ``pm_interactions`` for ``pm_sub``.
        pm_sub:       PM identifier used to label the result.

    Returns:
        Populated :class:`FrequencyStats` instance.
    """
    stats = FrequencyStats(pm_sub=pm_sub)

    call_counts: dict[str, int] = defaultdict(int)
    tod: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    desk: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for row in interactions:
        tool = row.get("tool_name", "unknown")
        ts = row.get("timestamp")

        call_counts[tool] += 1

        # Time-of-day distribution
        if isinstance(ts, datetime):
            hour = ts.hour
        elif isinstance(ts, str):
            try:
                hour = datetime.fromisoformat(ts).hour
            except ValueError:
                hour = 0
        else:
            hour = 0
        tod[tool][hour] += 1

        # Desk distribution — pm_desk is a list in the DB
        desks = row.get("pm_desk") or []
        if isinstance(desks, str):
            desks = [desks]
        for d in desks:
            if d:
                desk[tool][d] += 1

    stats.tool_call_counts = dict(call_counts)
    stats.time_of_day_dist = {t: dict(h) for t, h in tod.items()}
    stats.desk_dist = {t: dict(d) for t, d in desk.items()}
    stats.total_calls = sum(call_counts.values())

    # Primary tools = top 5 by call count
    stats.primary_tools = [
        t for t, _ in sorted(call_counts.items(), key=lambda x: -x[1])[:5]
    ]

    log.debug(
        "frequency_analysis_complete",
        pm_sub=pm_sub,
        total_calls=stats.total_calls,
        unique_tools=len(call_counts),
    )
    return stats
