"""
suggest_next_action tool implementation.

Loads the PM's latest heuristic model and returns the top-3 most probable
next tool calls given the current context.  Falls back gracefully when no
model exists (insufficient interaction history) or when the current tool
has no outgoing transitions.

Monotonic convergence guaranteed by SOS framework (Łojasiewicz inequality):
suggestions are derived from a converged HeuristicModel whose transition
matrix is guaranteed to be a fixed point of the ECEF iteration.
"""

from __future__ import annotations

from typing import Any, Optional

import structlog

from cognitive_server.ecef.equilibrium import ECEFEngine
from cognitive_server.ecef.models import HeuristicModel

log = structlog.get_logger("cognitive.tools.suggest")

_engine = ECEFEngine()


async def suggest_next_action(
    pm_sub: str,
    context: str,
    current_tool: Optional[str],
    desk: str,
) -> dict[str, Any]:
    """
    Return the top-3 most probable next tool calls for ``pm_sub``.

    Uses the latest converged :class:`HeuristicModel` to look up the
    transition row for ``current_tool`` and returns up to three candidates
    sorted by descending probability.

    If no model has been built yet (new PM or insufficient history), the
    response indicates that and suggests the user continues working to
    accumulate interaction history.

    Args:
        pm_sub:       JWT ``sub`` claim of the requesting PM.
        context:      Free-text description of what the PM is currently doing.
                      Used for logging and may inform future context-aware
                      suggestions.
        current_tool: The most recently executed tool, or ``None`` if this is
                      the start of a session.
        desk:         Trading desk identifier from the PM's JWT claims.

    Returns:
        Dict with keys:
        - ``suggestions``: list of ``{tool, probability, rank}`` dicts.
        - ``model_version``: int version of the model used.
        - ``confidence``: overall model confidence (evaluator accuracy).
        - ``message``: human-readable status string.
    """
    log.info(
        "suggest_next_action",
        pm_sub=pm_sub,
        current_tool=current_tool,
        desk=desk,
    )

    model: HeuristicModel = await _engine.get_or_build_model(pm_sub)

    # No transitions at all — model is empty
    if not model.transitions:
        return {
            "suggestions": [],
            "model_version": model.version,
            "confidence": 0.0,
            "message": (
                "Insufficient interaction history to generate suggestions. "
                "Continue using MCP tools to build your cognitive profile."
            ),
        }

    # No current_tool provided — return globally most-called tools as seed
    if not current_tool:
        # Aggregate all outgoing transition probabilities to rank tools
        tool_scores: dict[str, float] = {}
        for from_tool, edges in model.transitions.items():
            for to_tool, prob in edges.items():
                tool_scores[to_tool] = tool_scores.get(to_tool, 0.0) + prob

        top = sorted(tool_scores.items(), key=lambda x: -x[1])[:3]
        suggestions = [
            {"tool": tool, "probability": round(prob, 4), "rank": rank + 1}
            for rank, (tool, prob) in enumerate(top)
        ]
        return {
            "suggestions": suggestions,
            "model_version": model.version,
            "confidence": round(model.confidence, 4),
            "message": "Session start — showing globally most likely tools.",
        }

    # Predict from current_tool's transition row
    predictions = model.predict_next(current_tool, top_k=3)

    if not predictions:
        return {
            "suggestions": [],
            "model_version": model.version,
            "confidence": round(model.confidence, 4),
            "message": (
                f"No transitions observed from '{current_tool}' yet. "
                "Suggestions will improve as more data is collected."
            ),
        }

    suggestions = [
        {"tool": tool, "probability": round(prob, 4), "rank": rank + 1}
        for rank, (tool, prob) in enumerate(predictions)
    ]

    return {
        "suggestions": suggestions,
        "model_version": model.version,
        "confidence": round(model.confidence, 4),
        "message": f"Top {len(suggestions)} suggestions from '{current_tool}'.",
    }
