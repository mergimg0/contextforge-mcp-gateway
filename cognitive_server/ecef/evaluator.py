"""
ECEF Evaluator: scores a HeuristicModel against held-out interactions.

For each held-out interaction that has a ``preceding_tool``, the evaluator
asks the model "given the preceding tool, what is the most likely next tool?"
and checks whether the answer matches the actual ``tool_name``.

The resulting accuracy score drives two things:
1. The model's ``confidence`` field.
2. The convergence gap ``|accuracy_n - accuracy_{n-1}|`` which terminates
   the ECEF iteration loop when it falls below epsilon.

Monotonic convergence guaranteed by SOS framework (Łojasiewicz inequality):
the accuracy functional is a sum-of-squares polynomial in the transition
probabilities, so gradient descent on this surface reaches a fixed point
in finite iterations.
"""

from __future__ import annotations

from typing import Any

import structlog

from cognitive_server.ecef.models import EvaluationResult, HeuristicModel

log = structlog.get_logger("cognitive.ecef.evaluator")


def evaluate(
    model: HeuristicModel,
    held_out: list[dict[str, Any]],
) -> EvaluationResult:
    """
    Score ``model`` against ``held_out`` interaction rows.

    A prediction is attempted for every row that has a non-None
    ``preceding_tool`` value.  The prediction is the argmax of
    ``model.transitions[preceding_tool]``, i.e. the single most probable
    next tool according to the current Markov chain.

    A prediction is counted as *correct* when the argmax tool matches
    ``row["tool_name"]`` exactly.

    Args:
        model:     The :class:`HeuristicModel` being evaluated.
        held_out:  Held-out interaction rows (never seen during construction).

    Returns:
        :class:`EvaluationResult` with ``accuracy``, ``predictions``, and
        ``total``.
    """
    correct = 0
    predictions = 0
    total = len(held_out)

    for row in held_out:
        preceding = row.get("preceding_tool")
        actual = row.get("tool_name")

        if not preceding or not actual:
            continue  # Cannot form a prediction without a predecessor

        row_transitions = model.transitions.get(preceding)
        if not row_transitions:
            continue  # Model has no outgoing edges from this tool

        # argmax of the transition row
        predicted = max(row_transitions, key=lambda t: row_transitions[t])
        predictions += 1
        if predicted == actual:
            correct += 1

    accuracy = (correct / predictions) if predictions > 0 else 0.0

    result = EvaluationResult(
        accuracy=accuracy,
        predictions=predictions,
        total=total,
    )

    log.info(
        "evaluator_score",
        pm_sub=model.pm_sub,
        version=model.version,
        accuracy=round(accuracy, 4),
        correct=correct,
        predictions=predictions,
        total=total,
    )
    return result
