"""Risk MCP tool implementations.

Three tools: calculate_var, get_greeks, run_scenario.
All tools enforce desk-level PM isolation before returning data.
"""

from __future__ import annotations

import structlog

from mcp.server.fastmcp import Context

from shared.isolation import DeskIsolation
from shared.models import GreeksQuery, RiskQuery, ScenarioParams
from risk.engine import aggregate_greeks, calculate_var, run_scenario

logger = structlog.get_logger(__name__)


async def tool_calculate_var(query: RiskQuery, ctx: Context) -> dict:
    """
    Calculate Value-at-Risk (VaR) or Conditional VaR (CVaR) for a trading desk.

    Returns portfolio-level risk metrics using historical simulation over a
    configurable confidence level and holding-period horizon. Covers all standard
    risk metrics: var, cvar, delta, gamma, vega, theta, rho.

    NOT for: market data, price quotes, or security reference data
    (use Bloomberg tools for live prices, yields, and market feeds).

    NOT for: analyst reports, fundamentals, or research summaries
    (use Research tools for SEC filings, earnings estimates, and analyst commentary).

    NOT for: position-level inventory or trade blotter data
    (use Bloomberg tools for real-time position feeds).

    Example queries:
      - 1-day 99% VaR for the vol desk
      - 10-day 99.9% CVaR for rates desk
      - Current vega exposure for equities desk
    """
    subject, desk_access = DeskIsolation.enforce(ctx, query.desk, "calculate_var")

    logger.info(
        "calculate_var",
        subject=subject,
        desk=query.desk,
        metric=query.metric,
        confidence=query.confidence,
        horizon_days=query.horizon_days,
    )

    result = calculate_var(
        desk=query.desk,
        metric=query.metric,
        confidence=query.confidence,
        horizon_days=query.horizon_days,
    )

    result["requested_by"] = subject
    return result


async def tool_get_greeks(query: GreeksQuery, ctx: Context) -> dict:
    """
    Retrieve aggregate portfolio Greeks for a trading desk.

    Returns delta, gamma, vega, theta, and rho at the portfolio level, plus
    a per-underlying breakdown of the top risk contributors. Optionally filter
    to options on a specific underlying (e.g., SPX, NVDA, UST10Y).

    Designed for options-heavy books with high vega and meaningful gamma.
    Values are in dollar-sensitivity terms (e.g., vega = USD per vol point,
    theta = USD per calendar day, rho = USD per basis point).

    NOT for: raw market Greeks from a pricing engine or analytics terminal
    (use Bloomberg tools for real-time option chain data and OTM strikes).

    NOT for: individual option contract specifications or implied vol surfaces
    (use Bloomberg tools for vol surface queries, OVDV, OMON).

    NOT for: credit risk, counterparty exposure, or margin requirements
    (those are separate risk dimensions outside this tool's scope).

    Example queries:
      - Portfolio Greeks for the vol desk
      - SPX-specific Greeks on the equities desk
      - Rate sensitivity (rho) breakdown for the rates desk
    """
    subject, desk_access = DeskIsolation.enforce(ctx, query.desk, "get_greeks")

    logger.info(
        "get_greeks",
        subject=subject,
        desk=query.desk,
        underlying=query.underlying,
    )

    result = aggregate_greeks(
        desk=query.desk,
        underlying=query.underlying,
    )

    result["requested_by"] = subject
    return result


async def tool_run_scenario(params: ScenarioParams, ctx: Context) -> dict:
    """
    Run a stress scenario against a desk's portfolio and return PnL impact.

    Supports four pre-defined scenarios with a severity magnitude multiplier:
      - vol_spike: implied volatility surge (e.g., VIX spike from 15 to 40)
      - rate_shock: parallel yield curve shift (+100bps base, scaled by magnitude)
      - equity_crash: simultaneous equity sell-off and vol explosion (-15% base)
      - custom: composite multi-factor stress combining the above

    Returns total PnL impact, decomposed by risk factor (delta/vega/gamma/rho/spread),
    the single worst-contributing position, a carry-based recovery estimate, and the
    expected shift in portfolio Greeks after the scenario materialises.

    NOT for: historical backtests or time-series scenario replay
    (use Research tools for historical event studies and factor attribution).

    NOT for: individual security stress testing or single-name CDS analysis
    (use Bloomberg tools for DLIB or single-name scenario functions).

    NOT for: regulatory stress tests (FRTB, CCAR, CECL) requiring official model approval
    (those are produced by the Risk Management system, not this tool).

    Example queries:
      - Vol spike at 2x severity on the vol desk
      - 150bps rate shock (magnitude=1.5) on the rates desk
      - Equity crash scenario on the equities desk
    """
    subject, desk_access = DeskIsolation.enforce(ctx, params.desk, "run_scenario")

    logger.info(
        "run_scenario",
        subject=subject,
        desk=params.desk,
        scenario=params.scenario,
        magnitude=params.magnitude,
    )

    result = run_scenario(
        desk=params.desk,
        scenario=params.scenario,
        magnitude=params.magnitude,
    )

    result["requested_by"] = subject
    return result
