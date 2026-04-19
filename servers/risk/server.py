"""Risk MCP server entry point.

Exposes three tools: calculate_var, get_greeks, run_scenario.
Runs on port 8011 with streamable-http transport.
JWT bearer auth validates the 'risk-mcp' audience and 'risk:read' scope.
"""

from __future__ import annotations

import sys
import os

# Allow importing shared/ as a top-level package when the container
# sets WORKDIR to /app/servers (i.e. shared/ and risk/ are siblings).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp import Context

from shared.models import GreeksQuery, RiskQuery, ScenarioParams
from risk.tools import tool_calculate_var, tool_get_greeks, tool_run_scenario

# ---------------------------------------------------------------------------
# Server construction — gateway handles auth, backend trusts gateway
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="contextforge-risk-mcp",
    instructions=(
        "Risk analytics server. "
        "Provides VaR/CVaR calculations, portfolio Greeks aggregation, "
        "and stress scenario analysis for authorised trading desks."
    ),
)


# ---------------------------------------------------------------------------
# Tool registrations — thin wrappers that delegate to tools.py
# ---------------------------------------------------------------------------

@mcp.tool()
async def calculate_var(query: RiskQuery, ctx: Context) -> dict:
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
    """
    return await tool_calculate_var(query, ctx)


@mcp.tool()
async def get_greeks(query: GreeksQuery, ctx: Context) -> dict:
    """
    Retrieve aggregate portfolio Greeks for a trading desk.

    Returns delta, gamma, vega, theta, and rho at the portfolio level, plus
    a per-underlying breakdown of the top risk contributors. Optionally filter
    to options on a specific underlying (e.g., SPX, NVDA, UST10Y).

    NOT for: raw market Greeks from a pricing engine or analytics terminal
    (use Bloomberg tools for real-time option chain data and OTM strikes).

    NOT for: individual option contract specifications or implied vol surfaces
    (use Bloomberg tools for vol surface queries, OVDV, OMON).

    NOT for: credit risk, counterparty exposure, or margin requirements
    (those are separate risk dimensions outside this tool's scope).
    """
    return await tool_get_greeks(query, ctx)


@mcp.tool()
async def run_scenario(params: ScenarioParams, ctx: Context) -> dict:
    """
    Run a stress scenario against a desk's portfolio and return PnL impact.

    Supports four pre-defined scenarios with a severity magnitude multiplier:
      - vol_spike: implied volatility surge (e.g., VIX spike from 15 to 40)
      - rate_shock: parallel yield curve shift (+100bps base, scaled by magnitude)
      - equity_crash: simultaneous equity sell-off and vol explosion (-15% base)
      - custom: composite multi-factor stress combining the above

    NOT for: historical backtests or time-series scenario replay
    (use Research tools for historical event studies and factor attribution).

    NOT for: individual security stress testing or single-name CDS analysis
    (use Bloomberg tools for DLIB or single-name scenario functions).

    NOT for: regulatory stress tests (FRTB, CCAR, CECL) requiring official model approval
    (those are produced by the Risk Management system, not this tool).
    """
    return await tool_run_scenario(params, ctx)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    os.environ.setdefault("MCP_HTTP_HOST", "0.0.0.0")
    os.environ.setdefault("MCP_HTTP_PORT", "8011")
    mcp.run(transport="streamable-http")
