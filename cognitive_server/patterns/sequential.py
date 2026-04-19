"""
Sequential pattern mining over PM tool-call sessions.

Uses a sliding-window approach over chronologically ordered session rows to
extract recurring tool chains.  A "chain" is a tuple of consecutive tool
names within the same ``session_id``.  This provides the raw material for
the ECEF constructor's Markov transition matrix.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import structlog

log = structlog.get_logger("cognitive.patterns.sequential")

# Default sliding-window length (number of consecutive tool calls per chain).
DEFAULT_WINDOW = 3


@dataclass
class ChainRecord:
    """
    A recurring tool-call chain with usage statistics.

    Attributes:
        chain:          Ordered tuple of tool names, e.g.
                        ``("get_ref_data", "calculate_risk")``.
        frequency:      Number of times this exact chain was observed.
        avg_duration_ms: Average wall-clock duration of the chain in ms
                        (from first-tool start to last-tool end), or ``None``
                        if latency data is unavailable.
    """

    chain: tuple[str, ...]
    frequency: int
    avg_duration_ms: float | None


def _group_by_session(
    interactions: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Partition interaction rows by ``session_id``, preserving timestamp order."""
    sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in interactions:
        sid = row.get("session_id", "_unknown_")
        sessions[sid].append(row)
    # Each session is already ordered by timestamp from the DB query but sort
    # defensively in case the caller provided an unsorted list.
    for sid in sessions:
        sessions[sid].sort(key=lambda r: r.get("timestamp", 0))
    return sessions


def mine_sequential_patterns(
    interactions: list[dict[str, Any]],
    window: int = DEFAULT_WINDOW,
    min_frequency: int = 2,
) -> list[ChainRecord]:
    """
    Extract recurring tool-call chains from a flat list of interaction rows.

    The algorithm:
    1. Group rows by ``session_id`` and sort by ``timestamp``.
    2. Slide a window of ``window`` consecutive calls over each session.
    3. Count chain occurrences and accumulate durations across sessions.
    4. Return chains with ``frequency >= min_frequency``, sorted by frequency.

    Args:
        interactions:  Flat list of row dicts from ``pm_interactions``.
        window:        Chain length in number of consecutive calls (default 3).
        min_frequency: Minimum occurrence count to include a chain in the
                       result (default 2).

    Returns:
        List of :class:`ChainRecord`, ordered by descending frequency.
    """
    if not interactions:
        return []

    chain_counts: dict[tuple[str, ...], int] = defaultdict(int)
    chain_durations: dict[tuple[str, ...], list[float]] = defaultdict(list)

    sessions = _group_by_session(interactions)

    for sid, rows in sessions.items():
        tools = [r.get("tool_name", "unknown") for r in rows]
        latencies = [r.get("latency_ms") for r in rows]

        # Slide window
        for i in range(len(tools) - window + 1):
            chain = tuple(tools[i : i + window])
            chain_counts[chain] += 1

            # Sum latencies within the window if available
            window_latencies = latencies[i : i + window]
            if all(lat is not None for lat in window_latencies):
                total_ms = sum(float(lat) for lat in window_latencies)  # type: ignore[arg-type]
                chain_durations[chain].append(total_ms)

    records: list[ChainRecord] = []
    for chain, freq in chain_counts.items():
        if freq < min_frequency:
            continue
        durations = chain_durations.get(chain)
        avg_dur = (sum(durations) / len(durations)) if durations else None
        records.append(ChainRecord(chain=chain, frequency=freq, avg_duration_ms=avg_dur))

    records.sort(key=lambda r: -r.frequency)

    log.debug(
        "sequential_mining_complete",
        sessions=len(sessions),
        chains_found=len(records),
        window=window,
        min_frequency=min_frequency,
    )
    return records
