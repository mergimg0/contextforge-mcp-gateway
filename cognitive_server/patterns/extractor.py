"""
Unified PatternExtractor that orchestrates sequential and frequency analysis.

The extractor is the primary interface between the raw TimescaleDB rows and
the ECEF constructor.  It coordinates both analysis modules and returns a
single :class:`PatternAnalysis` result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from cognitive_server.patterns.frequency import FrequencyStats, analyse_frequency
from cognitive_server.patterns.sequential import ChainRecord, mine_sequential_patterns

log = structlog.get_logger("cognitive.patterns.extractor")


@dataclass
class PatternAnalysis:
    """
    Combined output of sequential and frequency pattern analysis for one PM.

    Attributes:
        pm_sub:         PM identifier.
        frequency:      Frequency statistics (call counts, time-of-day, desk).
        chains:         Ranked list of recurring tool-call chains.
        raw_count:      Total raw interaction rows analysed.
        session_count:  Number of distinct sessions represented.
    """

    pm_sub: str
    frequency: FrequencyStats
    chains: list[ChainRecord] = field(default_factory=list)
    raw_count: int = 0
    session_count: int = 0


class PatternExtractor:
    """
    Orchestrates sequential and frequency pattern analysis.

    Intended to be instantiated once per ``pm_sub`` and called with a fresh
    batch of interaction rows.  Thread-safe for reads; not designed for
    concurrent writes to the same instance.
    """

    def __init__(
        self,
        sequential_window: int = 3,
        min_chain_frequency: int = 2,
    ) -> None:
        """
        Args:
            sequential_window:    Sliding-window length for chain mining.
            min_chain_frequency:  Chains observed fewer times are discarded.
        """
        self._window = sequential_window
        self._min_freq = min_chain_frequency

    def extract(
        self,
        interactions: list[dict[str, Any]],
        pm_sub: str,
    ) -> PatternAnalysis:
        """
        Run full pattern analysis on a list of raw interaction dicts.

        Args:
            interactions: Rows from ``pm_interactions`` for ``pm_sub``.
            pm_sub:       PM identifier.

        Returns:
            :class:`PatternAnalysis` containing both frequency and sequential
            results.
        """
        log.info(
            "pattern_extraction_start",
            pm_sub=pm_sub,
            n_rows=len(interactions),
        )

        frequency = analyse_frequency(interactions, pm_sub=pm_sub)

        chains = mine_sequential_patterns(
            interactions,
            window=self._window,
            min_frequency=self._min_freq,
        )

        session_ids = {r.get("session_id") for r in interactions if r.get("session_id")}

        analysis = PatternAnalysis(
            pm_sub=pm_sub,
            frequency=frequency,
            chains=chains,
            raw_count=len(interactions),
            session_count=len(session_ids),
        )

        log.info(
            "pattern_extraction_complete",
            pm_sub=pm_sub,
            total_calls=frequency.total_calls,
            chains_found=len(chains),
            sessions=len(session_ids),
        )
        return analysis
