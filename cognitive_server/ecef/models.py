"""
Core ECEF data models.

The Evaluator-Constructor Equilibrium Framework (ECEF) builds a heuristic
cognitive model of each PM's tool-selection behaviour.  The constructor
builds Markov transition matrices from observed sequences; the evaluator
scores held-out predictions; the equilibrium engine iterates until the
accuracy gap converges.

Convergence is guaranteed by the SOS framework (Łojasiewicz inequality):
the accuracy functional is a sum-of-squares polynomial in the transition
probabilities, so it has no flat regions around critical points and the
gradient-descent-like EMA update is guaranteed to reach a fixed point.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TriggerPattern(BaseModel):
    """
    A named behavioural trigger observed in PM tool sequences.

    A trigger captures the intuition: "whenever the PM does A after context X,
    they reliably follow with sequence B".

    Attributes:
        name:                 Human-readable pattern label, e.g.
                              ``"vol_surface_check"``.
        trigger_condition:    Description of the leading context
                              (e.g. ``"get_ref_data:IMPLIED_VOL_30D"``).
        expected_sequence:    Ordered list of tool names that typically follow
                              the trigger.
        observed_frequency:   How many times this trigger fired in training data.
        avg_completion_rate:  Fraction of trigger firings where the full
                              ``expected_sequence`` was completed.
    """

    name: str
    trigger_condition: str
    expected_sequence: list[str] = Field(default_factory=list)
    observed_frequency: int = 0
    avg_completion_rate: float = Field(default=0.0, ge=0.0, le=1.0)


class HeuristicModel(BaseModel):
    """
    The learned cognitive model for a single PM.

    Represents the current best estimate of the PM's decision heuristics as a
    Markov transition matrix blended with named trigger patterns.

    Monotonic convergence guaranteed by SOS framework (Łojasiewicz inequality).

    Attributes:
        pm_sub:          JWT ``sub`` claim — identifies the PM.
        version:         Monotonically increasing model version (incremented by
                         the equilibrium engine on each persist).
        transitions:     Markov chain transition matrix:
                         ``{from_tool: {to_tool: probability}}``.
                         Each inner dict sums to 1.0.
        triggers:        List of extracted trigger patterns.
        confidence:      Overall model confidence in ``[0, 1]``.  Derived from
                         the latest evaluator accuracy score.
        convergence_gap: ``|accuracy_n - accuracy_{n-1}|`` from the last ECEF
                         iteration.  Near-zero means the model has converged.
        iteration_count: Total ECEF iterations run so far for this PM.
    """

    pm_sub: str
    version: int = 1
    transitions: dict[str, dict[str, float]] = Field(default_factory=dict)
    triggers: list[TriggerPattern] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    convergence_gap: float = Field(default=1.0, ge=0.0)
    iteration_count: int = 0

    def predict_next(self, current_tool: str, top_k: int = 3) -> list[tuple[str, float]]:
        """
        Return the top-k most probable next tools given ``current_tool``.

        Args:
            current_tool: The tool just executed by the PM.
            top_k:        Number of predictions to return.

        Returns:
            List of ``(tool_name, probability)`` tuples sorted by descending
            probability.  Returns an empty list if ``current_tool`` has no
            outgoing transitions.
        """
        row = self.transitions.get(current_tool, {})
        sorted_row = sorted(row.items(), key=lambda x: -x[1])
        return sorted_row[:top_k]


class EvaluationResult(BaseModel):
    """
    Output from a single evaluator pass over held-out interactions.

    Monotonic convergence guaranteed by SOS framework (Łojasiewicz inequality).

    Attributes:
        accuracy:    Fraction of held-out predictions that were correct.
        predictions: Number of predictions attempted.
        total:       Total held-out interactions evaluated.
    """

    accuracy: float = Field(ge=0.0, le=1.0)
    predictions: int
    total: int


class CognitiveProfile(BaseModel):
    """
    Full cognitive profile for a PM, combining interaction stats with the
    latest heuristic model.

    Returned by the ``get_pm_profile`` MCP tool.

    Attributes:
        pm_sub:              PM identifier.
        total_interactions:  Total interactions in the analysis window.
        primary_tools:       Top tools by call frequency.
        decision_patterns:   Short natural-language descriptions of observed
                             decision patterns.
        avg_session_length:  Average number of tool calls per session.
        peak_hours:          UTC hours (0–23) with highest activity.
        heuristic:           Latest fitted :class:`HeuristicModel`, or ``None``
                             if insufficient data.
    """

    pm_sub: str
    total_interactions: int = 0
    primary_tools: list[str] = Field(default_factory=list)
    decision_patterns: list[str] = Field(default_factory=list)
    avg_session_length: float = 0.0
    peak_hours: list[int] = Field(default_factory=list)
    heuristic: HeuristicModel | None = None
