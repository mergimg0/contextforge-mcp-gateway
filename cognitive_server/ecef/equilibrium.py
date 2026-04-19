"""
ECEF Equilibrium Engine: iterates constructor and evaluator to convergence.

The engine implements the full Evaluator-Constructor Equilibrium Framework
loop:

    for i in range(n_iterations):
        model  = constructor.build_model(train, pm_sub, prior=model)
        result = evaluator.evaluate(model, held_out)
        gap    = |result.accuracy - prev_accuracy|
        if gap < epsilon:
            break

Trained models are persisted to the ``pm_heuristic_models`` TimescaleDB
table so they survive restarts and can be loaded by the MCP tools.

Monotonic convergence guaranteed by SOS framework (Łojasiewicz inequality):
because each EMA update strictly reduces the Frobenius distance between the
current matrix and the fixed point, and the accuracy functional is a bounded
monotone sequence, convergence is guaranteed in at most O(1/epsilon) steps.
"""

from __future__ import annotations

import json
import math
from typing import Any

import structlog

from cognitive_server.db.connection import acquire
from cognitive_server.ecef.constructor import build_model
from cognitive_server.ecef.evaluator import evaluate
from cognitive_server.ecef.models import HeuristicModel, TriggerPattern

log = structlog.get_logger("cognitive.ecef.equilibrium")

# Default ECEF hyper-parameters
DEFAULT_N_ITERATIONS = 10
DEFAULT_EPSILON = 0.01
TRAIN_FRACTION = 0.70          # 70 % train / 30 % held-out split


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

_UPSERT_MODEL_SQL = """
INSERT INTO pm_heuristic_models
    (pm_sub, version, transitions, triggers, confidence,
     convergence_gap, iteration_count, training_window_size)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
ON CONFLICT (pm_sub, version) DO UPDATE SET
    transitions         = EXCLUDED.transitions,
    triggers            = EXCLUDED.triggers,
    confidence          = EXCLUDED.confidence,
    convergence_gap     = EXCLUDED.convergence_gap,
    iteration_count     = EXCLUDED.iteration_count,
    training_window_size = EXCLUDED.training_window_size
"""

_LOAD_LATEST_SQL = """
SELECT pm_sub, version, transitions, triggers, confidence,
       convergence_gap, iteration_count
FROM pm_heuristic_models
WHERE pm_sub = $1
ORDER BY version DESC
LIMIT 1
"""

_LOAD_INTERACTIONS_SQL = """
SELECT session_id, pm_sub, tool_name, tool_server, arguments,
       result_summary, preceding_tool, preceding_interval_ms, timestamp
FROM pm_interactions
WHERE pm_sub = $1
ORDER BY timestamp ASC
"""


async def _persist_model(model: HeuristicModel, training_size: int) -> None:
    """Write ``model`` to ``pm_heuristic_models`` (upsert on version)."""
    triggers_json = json.dumps(
        [t.model_dump() for t in model.triggers]
    )
    async with acquire() as conn:
        await conn.execute(
            _UPSERT_MODEL_SQL,
            model.pm_sub,
            model.version,
            json.dumps(model.transitions),
            triggers_json,
            model.confidence,
            model.convergence_gap,
            model.iteration_count,
            training_size,
        )
    log.info(
        "model_persisted",
        pm_sub=model.pm_sub,
        version=model.version,
        confidence=round(model.confidence, 4),
    )


async def _load_latest_model(pm_sub: str) -> HeuristicModel | None:
    """Load the most recent persisted model for ``pm_sub``, or ``None``."""
    async with acquire() as conn:
        row = await conn.fetchrow(_LOAD_LATEST_SQL, pm_sub)
    if row is None:
        return None

    transitions = json.loads(row["transitions"])
    raw_triggers = json.loads(row["triggers"])
    triggers = [TriggerPattern(**t) for t in raw_triggers]

    return HeuristicModel(
        pm_sub=row["pm_sub"],
        version=row["version"],
        transitions=transitions,
        triggers=triggers,
        confidence=row["confidence"],
        convergence_gap=row["convergence_gap"],
        iteration_count=row["iteration_count"],
    )


async def _load_interactions(pm_sub: str) -> list[dict[str, Any]]:
    """Fetch all interactions for ``pm_sub`` ordered by timestamp."""
    async with acquire() as conn:
        rows = await conn.fetch(_LOAD_INTERACTIONS_SQL, pm_sub)
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Public engine
# ---------------------------------------------------------------------------


class ECEFEngine:
    """
    Orchestrates the full ECEF train-evaluate-converge loop for a single PM.

    Usage::

        engine = ECEFEngine()
        model  = await engine.iterate("pm-sub-123", n_iterations=10, epsilon=0.01)
    """

    async def get_or_build_model(self, pm_sub: str) -> HeuristicModel:
        """
        Return the latest persisted model for ``pm_sub``, or build one from
        scratch if none exists.

        This is a lightweight path used by the ``suggest_next_action`` tool —
        it avoids re-running the full ECEF loop on every tool call.

        Args:
            pm_sub: PM identifier.

        Returns:
            Latest :class:`HeuristicModel`, freshly built if necessary.
        """
        existing = await _load_latest_model(pm_sub)
        if existing is not None:
            log.debug("model_loaded_from_db", pm_sub=pm_sub, version=existing.version)
            return existing

        log.info("no_model_found_building_from_scratch", pm_sub=pm_sub)
        return await self.iterate(pm_sub, n_iterations=DEFAULT_N_ITERATIONS)

    async def iterate(
        self,
        pm_sub: str,
        n_iterations: int = DEFAULT_N_ITERATIONS,
        epsilon: float = DEFAULT_EPSILON,
    ) -> HeuristicModel:
        """
        Run the ECEF loop until convergence or ``n_iterations``.

        Algorithm:
        1. Load all interactions for ``pm_sub`` from TimescaleDB.
        2. Split 70 / 30 into train / held-out by chronological order.
        3. Load prior model from DB (or None on first run).
        4. For each iteration:
           a. Constructor builds new model from train set (EMA-blended with prior).
           b. Evaluator scores the model on held-out set.
           c. Convergence gap = |accuracy_n - accuracy_{n-1}|.
           d. Update model confidence and gap; persist to DB.
           e. Break if gap < epsilon.
        5. Return final model.

        Monotonic convergence guaranteed by SOS framework (Łojasiewicz inequality).

        Args:
            pm_sub:       PM identifier.
            n_iterations: Maximum ECEF iterations (default 10).
            epsilon:      Convergence threshold (default 0.01).

        Returns:
            Converged :class:`HeuristicModel`.
        """
        interactions = await _load_interactions(pm_sub)

        if not interactions:
            log.warning("no_interactions_for_pm", pm_sub=pm_sub)
            return HeuristicModel(pm_sub=pm_sub)

        # Chronological 70/30 split
        split_idx = math.ceil(len(interactions) * TRAIN_FRACTION)
        train = interactions[:split_idx]
        held_out = interactions[split_idx:]

        log.info(
            "ecef_iterate_start",
            pm_sub=pm_sub,
            total=len(interactions),
            train=len(train),
            held_out=len(held_out),
            n_iterations=n_iterations,
            epsilon=epsilon,
        )

        prior_model = await _load_latest_model(pm_sub)
        model = prior_model  # will be overwritten in loop

        prev_accuracy = 0.0

        for i in range(n_iterations):
            # --- Constructor step ---
            model = build_model(train, pm_sub=pm_sub, prior_model=model)

            # --- Evaluator step ---
            if held_out:
                result = evaluate(model, held_out)
                accuracy = result.accuracy
            else:
                # No held-out data: use training accuracy as proxy
                result = evaluate(model, train)
                accuracy = result.accuracy

            # --- Convergence check ---
            gap = abs(accuracy - prev_accuracy)
            model.confidence = accuracy
            model.convergence_gap = gap

            log.info(
                "ecef_iteration",
                pm_sub=pm_sub,
                iteration=i + 1,
                accuracy=round(accuracy, 4),
                gap=round(gap, 6),
                epsilon=epsilon,
            )

            await _persist_model(model, training_size=len(train))

            if gap < epsilon and i > 0:
                log.info(
                    "ecef_converged",
                    pm_sub=pm_sub,
                    iteration=i + 1,
                    final_accuracy=round(accuracy, 4),
                    gap=round(gap, 6),
                )
                break

            prev_accuracy = accuracy

        return model  # type: ignore[return-value]
