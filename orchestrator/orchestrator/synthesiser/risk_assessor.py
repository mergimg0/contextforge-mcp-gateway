"""
Risk Assessor — extracts risk dimensions from executor results and produces
a RiskAssessment with an overall LOW / MEDIUM / HIGH / EXTREME score.

All assessment is rule-based and deterministic.

Scoring logic:
  1. Scan for scenario results — worst P&L impact drives the base score.
  2. Scan for VaR / CVaR results — large tail risk elevates the score.
  3. Scan for Greeks — extreme vega / delta concentration elevates the score.
  4. Apply modifiers: multiple independent risk signals → score up one level.

Risk score thresholds:
  LOW     → scenario loss < 2%, VaR < 1%
  MEDIUM  → scenario loss 2–5%  OR  VaR 1–3%
  HIGH    → scenario loss 5–10% OR  VaR 3–5%  OR extreme Greeks
  EXTREME → scenario loss > 10% OR  VaR > 5%
"""

from __future__ import annotations

from typing import Any

import structlog

from ..executor.models import ToolCallResult
from .models import RiskAssessment

log = structlog.get_logger("orchestrator.synthesiser.risk_assessor")

# Thresholds (all expressed as positive fractions of portfolio notional)
_VAR_MEDIUM   = 0.01
_VAR_HIGH     = 0.03
_VAR_EXTREME  = 0.05

_SCENARIO_MEDIUM  = 0.02
_SCENARIO_HIGH    = 0.05
_SCENARIO_EXTREME = 0.10

_VEGA_CONCENTRATION_HIGH    = 200_000   # absolute vega units
_DELTA_CONCENTRATION_HIGH   = 500_000   # absolute delta units


def assess_risk(results: list[ToolCallResult]) -> RiskAssessment:
    """
    Derive a RiskAssessment from the list of executor results.

    Only processes results from the 'risk' server.  Bloomberg and research
    results are ignored here — they contribute to evidence scoring instead.

    Args:
        results: All ToolCallResults from the executor.

    Returns:
        Populated RiskAssessment with risk_score set.
    """
    scenario_pnl: float | None = None
    scenario_name: str | None = None
    var_value: float | None = None
    var_metric: str = "VaR"
    var_horizon: int = 1
    vega: float | None = None
    delta: float | None = None

    for result in results:
        if result.call.server != "risk" or not result.success or not result.data:
            continue

        data = result.data
        tool = result.call.tool

        if tool == "run_scenario":
            pnl = _safe_float(
                data.get("pnl_impact") or data.get("total_pnl") or data.get("pnl")
            )
            if pnl is not None and (scenario_pnl is None or pnl < scenario_pnl):
                scenario_pnl = pnl
                scenario_name = data.get("scenario", result.call.arguments.get("params", {}).get("scenario", "stress"))

        elif tool == "calculate_var":
            val = _safe_float(data.get("var") or data.get("cvar") or data.get("VaR") or data.get("CVaR"))
            if val is not None:
                var_value = val
                var_metric = str(data.get("metric", "var")).upper()
                var_horizon = int(data.get("horizon_days", 1))

        elif tool == "get_greeks":
            portfolio = data.get("portfolio") or data
            v = _safe_float(portfolio.get("vega"))
            d = _safe_float(portfolio.get("delta"))
            if v is not None:
                vega = v
            if d is not None:
                delta = d

    # ----------------------------------------------------------------
    # Determine risk score
    # ----------------------------------------------------------------
    risk_score = _compute_risk_score(scenario_pnl, var_value, vega, delta)

    # ----------------------------------------------------------------
    # Build narrative fields
    # ----------------------------------------------------------------
    max_loss_scenario = _narrative_scenario(scenario_pnl, scenario_name)
    portfolio_impact = _narrative_portfolio_impact(scenario_pnl, var_value, var_metric, var_horizon)
    concentration_risk = _narrative_concentration(vega, delta)
    var_estimate = _narrative_var(var_value, var_metric, var_horizon)
    greeks_summary = _narrative_greeks(vega, delta)

    log.info(
        "risk_assessed",
        risk_score=risk_score,
        scenario_pnl=scenario_pnl,
        var_value=var_value,
    )

    return RiskAssessment(
        max_loss_scenario=max_loss_scenario,
        portfolio_impact=portfolio_impact,
        concentration_risk=concentration_risk,
        var_estimate=var_estimate,
        greeks_summary=greeks_summary,
        risk_score=risk_score,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_risk_score(
    scenario_pnl: float | None,
    var_value: float | None,
    vega: float | None,
    delta: float | None,
) -> str:
    score_level = 0  # 0=LOW, 1=MEDIUM, 2=HIGH, 3=EXTREME

    # Scenario contribution
    if scenario_pnl is not None:
        loss = abs(scenario_pnl)
        if loss >= _SCENARIO_EXTREME:
            score_level = max(score_level, 3)
        elif loss >= _SCENARIO_HIGH:
            score_level = max(score_level, 2)
        elif loss >= _SCENARIO_MEDIUM:
            score_level = max(score_level, 1)

    # VaR contribution
    if var_value is not None:
        loss = abs(var_value)
        if loss >= _VAR_EXTREME:
            score_level = max(score_level, 3)
        elif loss >= _VAR_HIGH:
            score_level = max(score_level, 2)
        elif loss >= _VAR_MEDIUM:
            score_level = max(score_level, 1)

    # Greeks concentration contribution (elevates by at most 1 level)
    greeks_elevated = False
    if vega is not None and abs(vega) >= _VEGA_CONCENTRATION_HIGH:
        greeks_elevated = True
    if delta is not None and abs(delta) >= _DELTA_CONCENTRATION_HIGH:
        greeks_elevated = True
    if greeks_elevated:
        score_level = min(3, score_level + 1)

    levels = ["LOW", "MEDIUM", "HIGH", "EXTREME"]
    return levels[score_level]


def _narrative_scenario(pnl: float | None, scenario_name: str | None) -> str | None:
    if pnl is None:
        return None
    name = scenario_name or "stress"
    loss_pct = abs(pnl) * 100
    direction = "loss" if pnl < 0 else "gain"
    return (
        f"{name.replace('_', ' ').title()} scenario: estimated {direction} of "
        f"{loss_pct:.1f}% of portfolio notional"
    )


def _narrative_portfolio_impact(
    scenario_pnl: float | None,
    var_value: float | None,
    var_metric: str,
    horizon_days: int,
) -> str | None:
    parts: list[str] = []
    if scenario_pnl is not None:
        parts.append(f"Stress scenario impact: {scenario_pnl:+.2%}")
    if var_value is not None:
        parts.append(f"{var_metric} ({horizon_days}d): {var_value:+.2%}")
    return "; ".join(parts) if parts else None


def _narrative_concentration(vega: float | None, delta: float | None) -> str | None:
    concerns: list[str] = []
    if vega is not None and abs(vega) >= _VEGA_CONCENTRATION_HIGH:
        concerns.append(f"high vega concentration ({vega:+,.0f})")
    if delta is not None and abs(delta) >= _DELTA_CONCENTRATION_HIGH:
        concerns.append(f"high delta concentration ({delta:+,.0f})")
    if concerns:
        return f"Concentration risk flagged: {', '.join(concerns)}. Review against desk risk limits."
    return "No material concentration risk identified in available Greeks data."


def _narrative_var(var_value: float | None, var_metric: str, horizon_days: int) -> str | None:
    if var_value is None:
        return None
    return f"{var_metric} ({horizon_days}-day): {var_value:+.2%} of portfolio notional"


def _narrative_greeks(vega: float | None, delta: float | None) -> str | None:
    parts: list[str] = []
    if delta is not None:
        parts.append(f"Delta {delta:+,.0f}")
    if vega is not None:
        parts.append(f"Vega {vega:+,.0f}")
    return "; ".join(parts) if parts else None


def _safe_float(val: object) -> float | None:
    if val is None:
        return None
    try:
        return float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
