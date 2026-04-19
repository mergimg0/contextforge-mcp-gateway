"""
Evidence Scorer — classifies tool call results as FOR, AGAINST, or NEUTRAL
with respect to the investment thesis.

All classification is rule-based using data thresholds so the output is
deterministic, auditable, and does not depend on an LLM.

Scoring philosophy:
  - Bloomberg market data provides the primary empirical evidence.
  - Risk tool results provide risk-context evidence (typically NEUTRAL or
    AGAINST when risk is extreme).
  - Research results provide qualitative corroboration (lower weight).

Confidence weights by source:
  bloomberg  → 0.85  (hard market data, high reliability)
  risk       → 0.80  (quantitative model output)
  research   → 0.65  (analyst opinion, subject to bias)
"""

from __future__ import annotations

from typing import Any

import structlog

from ..executor.models import ToolCallResult
from ..parser.models import ClaimType, Direction, ThesisStatement
from .models import EvidenceItem

log = structlog.get_logger("orchestrator.synthesiser.evidence_scorer")

# Source reliability weights
_SOURCE_WEIGHTS = {
    "bloomberg": 0.85,
    "risk": 0.80,
    "research": 0.65,
}

# Vol-mispricing thresholds
_VOL_PREMIUM_HIGH_PERCENTILE = 80.0   # IV-RV spread at or above this → thesis supported
_VOL_PREMIUM_LOW_PERCENTILE = 40.0    # Below this → thesis not supported

# Momentum thresholds
_RSI_OVERBOUGHT = 70.0
_RSI_OVERSOLD = 30.0
_MOMENTUM_RETURN_THRESHOLD = 0.10     # 10% 3-month return = meaningful momentum

# Spread / relative-value thresholds
_SPREAD_ZSCORE_EXTREME = 2.0          # z-score ≥ 2 supports mean-reversion thesis
_SPREAD_ZSCORE_MODERATE = 1.0

# Risk thresholds
_VAR_LARGE_PCT_OF_PORTFOLIO = 0.03    # VaR > 3% of portfolio → elevated risk signal
_SCENARIO_LOSS_LARGE = -0.05          # Scenario loss > 5% → negative risk evidence


def score_evidence(
    results: list[ToolCallResult],
    thesis: ThesisStatement,
) -> list[EvidenceItem]:
    """
    Convert a list of ToolCallResults into classified EvidenceItems.

    Each successful tool call result is analysed for signals that either
    support or contradict the thesis.  Failed calls generate a NEUTRAL
    evidence item noting the data gap.

    Args:
        results:  All ToolCallResults from the executor.
        thesis:   The parsed thesis being validated.

    Returns:
        List of EvidenceItem, ordered: bloomberg → risk → research.
    """
    evidence: list[EvidenceItem] = []

    for result in results:
        source_key = result.call.server
        weight = _SOURCE_WEIGHTS.get(source_key, 0.60)

        if not result.success:
            evidence.append(_make_data_gap_item(result))
            continue

        data = result.data or {}
        tool = result.call.tool

        if source_key == "bloomberg":
            evidence.extend(_score_bloomberg(tool, data, thesis, weight))
        elif source_key == "risk":
            evidence.extend(_score_risk(tool, data, thesis, weight))
        elif source_key == "research":
            evidence.extend(_score_research(tool, data, thesis, weight))

    return evidence


# ---------------------------------------------------------------------------
# Bloomberg scoring
# ---------------------------------------------------------------------------

def _score_bloomberg(
    tool: str,
    data: dict[str, Any],
    thesis: ThesisStatement,
    weight: float,
) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []

    if tool == "get_ref_data":
        items.extend(_score_ref_data(data, thesis, weight))
    elif tool == "get_history":
        items.extend(_score_history(data, thesis, weight))

    return items


def _score_ref_data(
    data: dict[str, Any],
    thesis: ThesisStatement,
    weight: float,
) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    ticker_data: dict[str, Any] = {}

    # data shape: {"data": {ticker: {field: value}}, "meta": {...}}
    raw = data.get("data", data)
    if raw:
        ticker_data = next(iter(raw.values()), {}) if isinstance(raw, dict) else {}

    iv = _safe_float(ticker_data.get("IMPLIED_VOL_30D"))
    rv = _safe_float(ticker_data.get("HIST_REALIZED_VOL_30D"))
    px = _safe_float(ticker_data.get("PX_LAST"))

    if iv is not None and rv is not None:
        iv_rv_spread = iv - rv
        spread_pct = (iv_rv_spread / rv * 100) if rv > 0 else 0.0

        if thesis.claim_type == ClaimType.VOL_MISPRICING:
            if iv_rv_spread > 4.0:
                items.append(EvidenceItem(
                    source="bloomberg/get_ref_data",
                    data_point=f"IV-RV spread: {iv:.1f}% IV vs {rv:.1f}% RV (+{iv_rv_spread:.1f} vols)",
                    classification="FOR",
                    confidence=min(0.90, weight + spread_pct / 200),
                    citation=f"Bloomberg snapshot: IV={iv:.1f}%, RV={rv:.1f}%",
                    reasoning=(
                        f"The {iv_rv_spread:.1f} vol-point IV-RV spread ({spread_pct:.0f}% premium) "
                        f"indicates options are pricing in significantly more risk than recent realised "
                        f"volatility justifies, supporting the thesis that implied vol is elevated relative "
                        f"to realised."
                    ),
                ))
            elif iv_rv_spread < -2.0:
                items.append(EvidenceItem(
                    source="bloomberg/get_ref_data",
                    data_point=f"IV-RV spread: {iv:.1f}% IV vs {rv:.1f}% RV ({iv_rv_spread:.1f} vols — IV BELOW RV)",
                    classification="AGAINST",
                    confidence=weight,
                    citation=f"Bloomberg snapshot: IV={iv:.1f}%, RV={rv:.1f}%",
                    reasoning=(
                        f"Implied vol ({iv:.1f}%) is trading {abs(iv_rv_spread):.1f} vols BELOW realised "
                        f"({rv:.1f}%), the opposite of the stated mispricing. The vol premium is negative, "
                        f"contradicting a long-vol thesis."
                    ),
                ))
            else:
                items.append(EvidenceItem(
                    source="bloomberg/get_ref_data",
                    data_point=f"IV-RV spread: {iv_rv_spread:+.1f} vols (within normal range)",
                    classification="NEUTRAL",
                    confidence=0.70,
                    citation=f"Bloomberg snapshot: IV={iv:.1f}%, RV={rv:.1f}%",
                    reasoning=(
                        f"The IV-RV spread of {iv_rv_spread:+.1f} vols is within the normal range "
                        f"(±4 vols). Additional historical context is needed to assess the thesis."
                    ),
                ))

    earn_date = ticker_data.get("EARN_ANNOUNCE_DT")
    if earn_date and thesis.claim_type in (ClaimType.EVENT_DRIVEN, ClaimType.VOL_MISPRICING):
        items.append(EvidenceItem(
            source="bloomberg/get_ref_data",
            data_point=f"Next earnings date: {earn_date}",
            classification="FOR",
            confidence=0.75,
            citation=f"Bloomberg EARN_ANNOUNCE_DT: {earn_date}",
            reasoning=(
                f"An upcoming earnings date ({earn_date}) provides a specific catalyst "
                f"consistent with the thesis time horizon and supports elevated implied vol "
                f"as a rational market response to event risk."
            ),
        ))

    if px is not None:
        items.append(EvidenceItem(
            source="bloomberg/get_ref_data",
            data_point=f"Current price: ${px:.2f}",
            classification="NEUTRAL",
            confidence=0.95,
            citation=f"Bloomberg PX_LAST: {px:.2f}",
            reasoning="Current price snapshot provides the reference level for trade entry and sizing.",
        ))

    return items


def _score_history(
    data: dict[str, Any],
    thesis: ThesisStatement,
    weight: float,
) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    bars: list[dict] = data.get("bars", [])
    ticker = data.get("ticker", "asset")

    if len(bars) < 10:
        return items

    # Compute price return over available history
    first_close = _safe_float(bars[0].get("PX_LAST"))
    last_close = _safe_float(bars[-1].get("PX_LAST"))
    price_return = None
    if first_close and last_close and first_close > 0:
        price_return = (last_close - first_close) / first_close

    # Collect IV and RV series for spread analysis
    iv_series = [_safe_float(b.get("IMPLIED_VOL_30D")) for b in bars]
    rv_series = [_safe_float(b.get("HIST_REALIZED_VOL_30D")) for b in bars]
    iv_valid = [v for v in iv_series if v is not None]
    rv_valid = [v for v in rv_series if v is not None]

    if thesis.claim_type == ClaimType.VOL_MISPRICING and iv_valid and rv_valid:
        spreads = [iv - rv for iv, rv in zip(iv_valid, rv_valid) if iv and rv]
        if spreads:
            current_spread = spreads[-1]
            avg_spread = sum(spreads) / len(spreads)
            max_spread = max(spreads)
            percentile = sum(1 for s in spreads if s <= current_spread) / len(spreads) * 100

            if percentile >= _VOL_PREMIUM_HIGH_PERCENTILE:
                items.append(EvidenceItem(
                    source=f"bloomberg/get_history ({ticker})",
                    data_point=(
                        f"IV-RV spread at {percentile:.0f}th percentile over {len(spreads)}-day history "
                        f"(current: {current_spread:.1f}v, avg: {avg_spread:.1f}v, max: {max_spread:.1f}v)"
                    ),
                    classification="FOR",
                    confidence=min(0.92, weight + (percentile - 80) / 100),
                    citation=f"Bloomberg {len(bars)}-bar history analysis",
                    reasoning=(
                        f"The current IV-RV spread of {current_spread:.1f} vols sits at the "
                        f"{percentile:.0f}th percentile of the historical distribution, representing "
                        f"an unusually elevated vol premium. Historical mean reversion from such "
                        f"extremes supports a short-vol position."
                    ),
                ))
            elif percentile <= _VOL_PREMIUM_LOW_PERCENTILE:
                items.append(EvidenceItem(
                    source=f"bloomberg/get_history ({ticker})",
                    data_point=(
                        f"IV-RV spread at {percentile:.0f}th percentile (current: {current_spread:.1f}v) — "
                        f"vol premium is BELOW average"
                    ),
                    classification="AGAINST",
                    confidence=weight,
                    citation=f"Bloomberg {len(bars)}-bar history analysis",
                    reasoning=(
                        f"At the {percentile:.0f}th percentile, the IV-RV spread is below its historical "
                        f"average, suggesting vol is not currently elevated relative to realised. "
                        f"This contradicts a thesis predicated on mispriced implied vol."
                    ),
                ))
            else:
                items.append(EvidenceItem(
                    source=f"bloomberg/get_history ({ticker})",
                    data_point=f"IV-RV spread at {percentile:.0f}th percentile (current: {current_spread:.1f}v)",
                    classification="NEUTRAL",
                    confidence=0.70,
                    citation=f"Bloomberg {len(bars)}-bar history analysis",
                    reasoning=(
                        f"The {percentile:.0f}th percentile reading for the IV-RV spread is within the "
                        f"normal historical range. The signal is not sufficiently extreme to strongly "
                        f"support or refute the thesis at this threshold."
                    ),
                ))

    if thesis.claim_type == ClaimType.MOMENTUM and price_return is not None:
        if thesis.direction in (Direction.LONG, Direction.LONG_VOL) and price_return > _MOMENTUM_RETURN_THRESHOLD:
            items.append(EvidenceItem(
                source=f"bloomberg/get_history ({ticker})",
                data_point=f"Price return over period: {price_return:+.1%}",
                classification="FOR",
                confidence=min(0.88, weight + price_return),
                citation=f"Bloomberg price history: {bars[0].get('date')} to {bars[-1].get('date')}",
                reasoning=(
                    f"A {price_return:+.1%} return over the lookback period demonstrates strong "
                    f"positive price momentum. The trend is consistent with the bullish thesis "
                    f"and supports continuation if fundamental conditions hold."
                ),
            ))
        elif thesis.direction == Direction.SHORT and price_return < -_MOMENTUM_RETURN_THRESHOLD:
            items.append(EvidenceItem(
                source=f"bloomberg/get_history ({ticker})",
                data_point=f"Price return over period: {price_return:+.1%}",
                classification="FOR",
                confidence=min(0.88, weight + abs(price_return)),
                citation=f"Bloomberg price history: {bars[0].get('date')} to {bars[-1].get('date')}",
                reasoning=(
                    f"A {price_return:+.1%} return confirms negative price momentum. "
                    f"The sustained decline supports the short thesis and suggests "
                    f"trend continuation risk is elevated."
                ),
            ))
        elif abs(price_return) < 0.03:
            items.append(EvidenceItem(
                source=f"bloomberg/get_history ({ticker})",
                data_point=f"Price return over period: {price_return:+.1%} (flat)",
                classification="AGAINST",
                confidence=0.72,
                citation=f"Bloomberg price history: {bars[0].get('date')} to {bars[-1].get('date')}",
                reasoning=(
                    f"A near-flat return of {price_return:+.1%} over the lookback period provides "
                    f"weak evidence for a momentum thesis. Price is not trending strongly in either "
                    f"direction, undermining the momentum signal."
                ),
            ))

    if thesis.claim_type in (ClaimType.MEAN_REVERSION, ClaimType.RELATIVE_VALUE):
        if last_close and iv_valid:
            rv_values = rv_valid if rv_valid else [0.0]
            avg_rv = sum(rv_values) / len(rv_values)
            latest_rv = rv_values[-1] if rv_values else avg_rv
            deviation_from_mean = (latest_rv - avg_rv) / avg_rv if avg_rv > 0 else 0.0

            if abs(deviation_from_mean) > 0.25:
                classification = "FOR" if deviation_from_mean > 0 else "NEUTRAL"
                items.append(EvidenceItem(
                    source=f"bloomberg/get_history ({ticker})",
                    data_point=(
                        f"Realised vol {deviation_from_mean:+.0%} from {len(rv_values)}-bar average "
                        f"(latest: {latest_rv:.1f}%, mean: {avg_rv:.1f}%)"
                    ),
                    classification=classification,
                    confidence=0.76,
                    citation=f"Bloomberg RV history analysis",
                    reasoning=(
                        f"Realised volatility is {abs(deviation_from_mean):.0%} {'above' if deviation_from_mean > 0 else 'below'} "
                        f"its historical average, indicating the instrument is in a "
                        f"{'stress' if deviation_from_mean > 0 else 'low-vol'} regime. "
                        f"Mean reversion in vol is consistent with spread normalisation."
                    ),
                ))

    return items


# ---------------------------------------------------------------------------
# Risk scoring
# ---------------------------------------------------------------------------

def _score_risk(
    tool: str,
    data: dict[str, Any],
    thesis: ThesisStatement,
    weight: float,
) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []

    if tool == "calculate_var":
        items.extend(_score_var(data, thesis, weight))
    elif tool == "get_greeks":
        items.extend(_score_greeks(data, thesis, weight))
    elif tool == "run_scenario":
        items.extend(_score_scenario(data, thesis, weight))

    return items


def _score_var(
    data: dict[str, Any],
    thesis: ThesisStatement,
    weight: float,
) -> list[EvidenceItem]:
    var_val = _safe_float(data.get("var") or data.get("VaR"))
    cvar_val = _safe_float(data.get("cvar") or data.get("CVaR"))
    metric = data.get("metric", "var")
    confidence = data.get("confidence", 0.99)
    horizon = data.get("horizon_days", 1)

    val = var_val or cvar_val
    if val is None:
        return []

    val_abs = abs(val)
    if val_abs > _VAR_LARGE_PCT_OF_PORTFOLIO:
        return [EvidenceItem(
            source="risk/calculate_var",
            data_point=f"{metric.upper()} ({confidence:.0%}, {horizon}d): {val:+.2%} of portfolio",
            classification="AGAINST",
            confidence=weight,
            citation=f"Risk system: {metric.upper()}={val:.2%} at {confidence:.0%} confidence",
            reasoning=(
                f"The {metric.upper()} of {val_abs:.2%} exceeds the {_VAR_LARGE_PCT_OF_PORTFOLIO:.0%} "
                f"threshold, indicating the proposed trade carries elevated tail risk. "
                f"Position sizing will need careful management relative to risk limits."
            ),
        )]
    else:
        return [EvidenceItem(
            source="risk/calculate_var",
            data_point=f"{metric.upper()} ({confidence:.0%}, {horizon}d): {val:+.2%} of portfolio",
            classification="NEUTRAL",
            confidence=weight,
            citation=f"Risk system: {metric.upper()}={val:.2%}",
            reasoning=(
                f"The {metric.upper()} of {val_abs:.2%} is within normal bounds, suggesting the "
                f"trade's tail risk is manageable. This supports position sizing consistent with "
                f"standard risk limits."
            ),
        )]


def _score_greeks(
    data: dict[str, Any],
    thesis: ThesisStatement,
    weight: float,
) -> list[EvidenceItem]:
    vega = _safe_float(data.get("vega") or (data.get("portfolio", {}) or {}).get("vega"))
    delta = _safe_float(data.get("delta") or (data.get("portfolio", {}) or {}).get("delta"))

    parts = []
    if vega is not None:
        parts.append(f"Vega: {vega:+,.0f}")
    if delta is not None:
        parts.append(f"Delta: {delta:+,.0f}")

    if not parts:
        return []

    summary = ", ".join(parts)

    # Classify based on thesis direction and current Greeks
    if thesis.claim_type == ClaimType.VOL_MISPRICING:
        if vega is not None and vega > 50_000:
            classification = "AGAINST"
            reasoning = (
                f"The desk already carries significant long vega ({vega:+,.0f}). "
                f"Adding further vol exposure increases concentration risk in a "
                f"single risk factor, which may breach risk limits."
            )
        elif vega is not None and vega < -50_000:
            classification = "FOR"
            reasoning = (
                f"The desk is currently short vega ({vega:+,.0f}), meaning a "
                f"long-vol position would reduce — rather than increase — overall "
                f"vol risk concentration, supporting the thesis from a portfolio construction "
                f"perspective."
            )
        else:
            classification = "NEUTRAL"
            reasoning = (
                f"Current Greeks ({summary}) show modest vol exposure, leaving "
                f"capacity to add the proposed vol position within normal risk limits."
            )
    else:
        classification = "NEUTRAL"
        reasoning = f"Portfolio Greeks snapshot ({summary}) provides context for sizing the proposed trade."

    return [EvidenceItem(
        source="risk/get_greeks",
        data_point=summary,
        classification=classification,
        confidence=weight - 0.05,
        citation="Risk system: portfolio Greeks aggregation",
        reasoning=reasoning,
    )]


def _score_scenario(
    data: dict[str, Any],
    thesis: ThesisStatement,
    weight: float,
) -> list[EvidenceItem]:
    pnl = _safe_float(data.get("pnl_impact") or data.get("total_pnl") or data.get("pnl"))
    scenario = data.get("scenario", "stress")
    magnitude = data.get("magnitude", 2.0)

    if pnl is None:
        return []

    if pnl < _SCENARIO_LOSS_LARGE:
        return [EvidenceItem(
            source="risk/run_scenario",
            data_point=f"{scenario} scenario (mag={magnitude}x): P&L impact {pnl:+.2%}",
            classification="AGAINST",
            confidence=weight,
            citation=f"Risk system: {scenario} stress scenario",
            reasoning=(
                f"Under the {scenario} stress scenario at {magnitude}x severity, the portfolio "
                f"would lose {abs(pnl):.2%}. This represents a meaningful adverse outcome and "
                f"highlights that the thesis carries material downside risk if conditions "
                f"move against the position."
            ),
        )]
    elif pnl > 0.02:
        return [EvidenceItem(
            source="risk/run_scenario",
            data_point=f"{scenario} scenario (mag={magnitude}x): P&L impact {pnl:+.2%}",
            classification="FOR",
            confidence=weight - 0.10,
            citation=f"Risk system: {scenario} stress scenario",
            reasoning=(
                f"The {scenario} scenario produces a positive P&L impact of {pnl:+.2%}, "
                f"suggesting the current portfolio is positioned to benefit from the "
                f"stress conditions that would accompany this thesis materialising."
            ),
        )]
    else:
        return [EvidenceItem(
            source="risk/run_scenario",
            data_point=f"{scenario} scenario (mag={magnitude}x): P&L impact {pnl:+.2%} (limited impact)",
            classification="NEUTRAL",
            confidence=0.70,
            citation=f"Risk system: {scenario} stress scenario",
            reasoning=(
                f"The {scenario} scenario has a modest P&L impact of {pnl:+.2%}, indicating "
                f"the portfolio has limited direct exposure to this stress factor. "
                f"The trade should be evaluated primarily on its own merits."
            ),
        )]


# ---------------------------------------------------------------------------
# Research scoring
# ---------------------------------------------------------------------------

def _score_research(
    tool: str,
    data: dict[str, Any],
    thesis: ThesisStatement,
    weight: float,
) -> list[EvidenceItem]:
    results = data.get("results", [])
    if not results:
        return [EvidenceItem(
            source="research/search_research",
            data_point="No analyst research found for this query",
            classification="NEUTRAL",
            confidence=0.50,
            citation="Research database: no matching documents",
            reasoning=(
                "The absence of recent analyst coverage does not invalidate the thesis "
                "but reduces the available qualitative corroboration. The quantitative "
                "evidence should be weighted more heavily in the absence of research."
            ),
        )]

    # Score based on sentiment keywords in titles/summaries
    positive_keywords = ["bullish", "outperform", "buy", "overweight", "positive", "upgrade", "strong"]
    negative_keywords = ["bearish", "underperform", "sell", "underweight", "negative", "downgrade", "weak", "caution"]

    positive_count = 0
    negative_count = 0
    titles = []

    for item in results[:3]:
        title = (item.get("title") or item.get("headline") or "").lower()
        summary = (item.get("summary") or item.get("abstract") or "").lower()
        text = f"{title} {summary}"
        titles.append(item.get("title") or item.get("headline") or "untitled")

        positive_count += sum(1 for kw in positive_keywords if kw in text)
        negative_count += sum(1 for kw in negative_keywords if kw in text)

    citation_text = "; ".join(f'"{t}"' for t in titles[:2])

    if positive_count > negative_count + 1:
        return [EvidenceItem(
            source="research/search_research",
            data_point=f"{len(results)} research notes found; sentiment skews positive ({positive_count} bullish signals)",
            classification="FOR",
            confidence=weight - 0.10,
            citation=f"Research: {citation_text}",
            reasoning=(
                f"Analyst research ({len(results)} notes) shows predominantly positive sentiment "
                f"with {positive_count} bullish signals vs {negative_count} bearish signals. "
                f"Analyst consensus lends qualitative support to the thesis."
            ),
        )]
    elif negative_count > positive_count + 1:
        return [EvidenceItem(
            source="research/search_research",
            data_point=f"{len(results)} research notes found; sentiment skews negative ({negative_count} bearish signals)",
            classification="AGAINST",
            confidence=weight - 0.10,
            citation=f"Research: {citation_text}",
            reasoning=(
                f"Analyst research ({len(results)} notes) shows predominantly negative sentiment "
                f"with {negative_count} bearish signals vs {positive_count} bullish signals. "
                f"Consensus caution is a headwind for the thesis."
            ),
        )]
    else:
        return [EvidenceItem(
            source="research/search_research",
            data_point=f"{len(results)} research notes found; mixed or neutral sentiment",
            classification="NEUTRAL",
            confidence=weight - 0.15,
            citation=f"Research: {citation_text}",
            reasoning=(
                f"Available analyst research ({len(results)} notes) shows balanced or mixed sentiment, "
                f"neither strongly supporting nor contradicting the thesis. "
                f"The quantitative data should be the primary driver of the verdict."
            ),
        )]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val: object) -> float | None:
    if val is None:
        return None
    try:
        return float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _make_data_gap_item(result: ToolCallResult) -> EvidenceItem:
    return EvidenceItem(
        source=f"{result.call.server}/{result.call.tool}",
        data_point=f"Data unavailable: {result.error or 'tool call failed'}",
        classification="NEUTRAL",
        confidence=0.40,
        citation=f"{result.call.server}/{result.call.tool}: failed",
        reasoning=(
            f"This data point could not be retrieved ({result.error or 'unknown error'}). "
            f"The absence of this data reduces validation completeness but does not "
            f"directly support or contradict the thesis."
        ),
    )
