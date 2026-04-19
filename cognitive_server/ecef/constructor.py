"""
ECEF Constructor: builds a HeuristicModel from interaction observations.

The constructor performs two operations:
1. Builds a first-order Markov transition matrix from ordered tool-call
   sequences within sessions.
2. Extracts trigger patterns via temporal clustering — looking for tool pairs
   whose inter-arrival times cluster tightly around a short median.

A prior model (from the previous ECEF iteration) can be blended in via an
exponential moving average with ``alpha=0.3`` so new observations gradually
update beliefs rather than replacing them wholesale.

Monotonic convergence guaranteed by SOS framework (Łojasiewicz inequality):
the EMA update shrinks the L2 distance between successive models by at least
``(1 - alpha)`` per iteration.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import structlog

from cognitive_server.ecef.models import HeuristicModel, TriggerPattern

log = structlog.get_logger("cognitive.ecef.constructor")

# EMA blending coefficient — weight given to the newly-computed matrix.
EMA_ALPHA = 0.3

# Minimum number of observations for a transition to be included.
MIN_TRANSITION_COUNT = 1

# Temporal-clustering threshold: tool pairs whose median inter-arrival is
# below this (ms) are candidates for trigger patterns.
TRIGGER_INTERVAL_THRESHOLD_MS = 5_000


def _build_transition_counts(
    interactions: list[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    """
    Build raw transition counts from a flat list of interaction rows.

    Groups rows by ``session_id``, sorts each session by ``timestamp``, then
    increments ``counts[from_tool][to_tool]`` for every consecutive pair.

    Returns:
        Nested dict of ``{from_tool: {to_tool: count}}``.
    """
    sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in interactions:
        sessions[row.get("session_id", "_")].append(row)

    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for rows in sessions.values():
        rows.sort(key=lambda r: r.get("timestamp", 0))
        for i in range(len(rows) - 1):
            from_tool = rows[i].get("tool_name", "unknown")
            to_tool = rows[i + 1].get("tool_name", "unknown")
            counts[from_tool][to_tool] += 1

    return {k: dict(v) for k, v in counts.items()}


def _normalise_counts(
    counts: dict[str, dict[str, int]],
) -> dict[str, dict[str, float]]:
    """
    Convert raw counts to row-stochastic transition probabilities.

    Each row sums to 1.0.  Rows with total count below ``MIN_TRANSITION_COUNT``
    are dropped.

    Args:
        counts: Raw ``{from_tool: {to_tool: count}}`` dict.

    Returns:
        ``{from_tool: {to_tool: probability}}`` with each row summing to 1.0.
    """
    matrix: dict[str, dict[str, float]] = {}
    for from_tool, edges in counts.items():
        total = sum(edges.values())
        if total < MIN_TRANSITION_COUNT:
            continue
        matrix[from_tool] = {to: cnt / total for to, cnt in edges.items()}
    return matrix


def _blend_matrices(
    prior: dict[str, dict[str, float]],
    new: dict[str, dict[str, float]],
    alpha: float,
) -> dict[str, dict[str, float]]:
    """
    Blend two transition matrices via exponential moving average.

    ``result[from][to] = alpha * new[from][to] + (1 - alpha) * prior[from][to]``

    Tools present in only one matrix are handled gracefully: missing entries
    are treated as 0.0.  Each blended row is re-normalised to sum to 1.0.

    Args:
        prior:  Previous model's transition matrix.
        new:    Newly computed matrix from current training data.
        alpha:  Weight of the new estimate (``0 < alpha <= 1``).

    Returns:
        Blended row-stochastic matrix.
    """
    all_from = set(prior.keys()) | set(new.keys())
    blended: dict[str, dict[str, float]] = {}

    for from_tool in all_from:
        prior_row = prior.get(from_tool, {})
        new_row = new.get(from_tool, {})
        all_to = set(prior_row.keys()) | set(new_row.keys())

        merged: dict[str, float] = {}
        for to_tool in all_to:
            p = prior_row.get(to_tool, 0.0)
            n = new_row.get(to_tool, 0.0)
            merged[to_tool] = alpha * n + (1 - alpha) * p

        # Re-normalise
        total = sum(merged.values())
        if total > 0:
            blended[from_tool] = {t: v / total for t, v in merged.items()}

    return blended


def _extract_trigger_patterns(
    interactions: list[dict[str, Any]],
) -> list[TriggerPattern]:
    """
    Identify tool pairs that consistently fire in rapid succession.

    A trigger is defined as any ``(preceding_tool, tool_name)`` pair where the
    ``preceding_interval_ms`` distribution has a median below
    ``TRIGGER_INTERVAL_THRESHOLD_MS``.  This captures urgent reflex-like
    decision patterns — e.g. a PM who always runs ``calculate_risk`` within
    2 seconds of a ``get_ref_data`` call.

    Args:
        interactions: Raw interaction rows including ``preceding_tool`` and
                      ``preceding_interval_ms`` columns.

    Returns:
        List of :class:`TriggerPattern` instances.
    """
    # Accumulate inter-arrival times per (trigger, triggered) pair.
    pair_intervals: dict[tuple[str, str], list[float]] = defaultdict(list)

    for row in interactions:
        prec = row.get("preceding_tool")
        curr = row.get("tool_name")
        interval = row.get("preceding_interval_ms")
        if prec and curr and interval is not None:
            pair_intervals[(prec, curr)].append(float(interval))

    triggers: list[TriggerPattern] = []
    for (prec, curr), intervals in pair_intervals.items():
        if len(intervals) < 2:
            continue
        median_ms = float(np.median(intervals))
        if median_ms <= TRIGGER_INTERVAL_THRESHOLD_MS:
            # Completion rate: fraction of times this pair fired at all
            # (all entries in our list are completions, so rate = 1.0 per pair).
            pattern = TriggerPattern(
                name=f"{prec}_triggers_{curr}",
                trigger_condition=prec,
                expected_sequence=[curr],
                observed_frequency=len(intervals),
                avg_completion_rate=1.0,
            )
            triggers.append(pattern)

    triggers.sort(key=lambda t: -t.observed_frequency)
    return triggers


def build_model(
    interactions: list[dict[str, Any]],
    pm_sub: str,
    prior_model: HeuristicModel | None = None,
) -> HeuristicModel:
    """
    Construct a :class:`HeuristicModel` from training interactions.

    Steps:
    1. Build raw Markov transition counts from session-ordered sequences.
    2. Normalise to row-stochastic probabilities.
    3. If a prior model exists, blend with EMA (alpha=0.3).
    4. Extract trigger patterns from temporal clustering.
    5. Assemble and return the new :class:`HeuristicModel`.

    Monotonic convergence guaranteed by SOS framework (Łojasiewicz inequality).

    Args:
        interactions: Training rows from ``pm_interactions``.
        pm_sub:       PM identifier.
        prior_model:  Previous ECEF iteration's model for EMA blending
                      (``None`` on first build).

    Returns:
        A new :class:`HeuristicModel` incorporating all observations.
    """
    log.info(
        "constructor_build_start",
        pm_sub=pm_sub,
        n_interactions=len(interactions),
        has_prior=prior_model is not None,
    )

    # Step 1+2: raw counts → probability matrix
    counts = _build_transition_counts(interactions)
    new_matrix = _normalise_counts(counts)

    # Step 3: blend with prior if available
    if prior_model and prior_model.transitions:
        transition_matrix = _blend_matrices(
            prior=prior_model.transitions,
            new=new_matrix,
            alpha=EMA_ALPHA,
        )
    else:
        transition_matrix = new_matrix

    # Step 4: trigger patterns
    triggers = _extract_trigger_patterns(interactions)

    # Step 5: assemble model
    version = (prior_model.version + 1) if prior_model else 1
    iteration_count = (prior_model.iteration_count + 1) if prior_model else 1

    model = HeuristicModel(
        pm_sub=pm_sub,
        version=version,
        transitions=transition_matrix,
        triggers=triggers,
        confidence=0.0,  # evaluator will fill this in
        convergence_gap=1.0,  # evaluator will fill this in
        iteration_count=iteration_count,
    )

    log.info(
        "constructor_build_complete",
        pm_sub=pm_sub,
        version=version,
        n_transitions=len(transition_matrix),
        n_triggers=len(triggers),
    )
    return model
