"""
Bloomberg MCP backend server.

Exposes three market-data tools via the MCP streamable-HTTP transport:
  - get_ref_data    : current snapshot fields (price, vol, greeks, etc.)
  - get_history     : historical OHLCV + vol time series
  - search_securities: ticker discovery

Authentication: BearerAuthProvider validates Keycloak-issued JWTs scoped to
"bloomberg:read".  Every tool call is additionally gated by DeskIsolation to
ensure PMs only access data for their authorised desk(s).

Entrypoint:
    python -m bloomberg.server
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import structlog
from datetime import date
from typing import Literal, Optional

from mcp.server.fastmcp import Context, FastMCP

from shared.models import DeskId

from .tools import (
    get_ref_data as _get_ref_data,
    get_history as _get_history,
    search_securities as _search_securities,
)

log = structlog.get_logger("bloomberg.server")

# ---------------------------------------------------------------------------
# Server setup
# Gateway handles auth (JWT validation + RFC 8693 token exchange).
# Backend trusts gateway — caller identity via X-Caller-Sub header.
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="bloomberg-mcp",
)


# ---------------------------------------------------------------------------
# Tool registrations
# ---------------------------------------------------------------------------

@mcp.tool()
def get_ref_data(
    tickers: list[str],
    fields: list[str],
    desk: DeskId,
    ctx: Context,
) -> dict:
    """
    Fetch Bloomberg reference / snapshot data for one or more securities.

    Returns a mapping of {ticker: {field: value}} for every requested ticker
    and field combination.  Missing fields are returned as null rather than
    omitted so callers can distinguish "field not available for this security"
    from "field not requested".

    USE THIS FOR:
      - End-of-day or real-time prices (PX_LAST, PX_OPEN, PX_HIGH, PX_LOW)
      - Volume and market cap (VOLUME, CUR_MKT_CAP)
      - Implied and realised volatility snapshots (IMPLIED_VOL_30D,
        HIST_REALIZED_VOL_30D)
      - Option greeks snapshots (OPT_DELTA, OPT_GAMMA, OPT_VEGA, OPT_THETA)
      - Corporate actions metadata (EARN_ANNOUNCE_DT, DVD_YILD)
      - Index / benchmark reference (PE_RATIO, EQY_WEIGHTED_AVG_PX)

    DO NOT USE FOR:
      - Portfolio-level risk metrics (delta, VaR, CVaR) — use calculate_risk
      - Stress scenarios or shock analysis — use run_scenario
      - Aggregated portfolio positions — use get_positions
      - Time-series / historical data — use get_history instead

    Args:
        tickers: Bloomberg tickers, e.g. ["AAPL US Equity", "SPX Index"].
                 Up to 50 tickers per request.
        fields:  Bloomberg field mnemonics, e.g. ["PX_LAST", "IMPLIED_VOL_30D"].
                 Unknown fields are returned as null without raising an error.
        desk:    Calling PM's trading desk.  Must match JWT desk_access claim.
        ctx:     MCP context carrying JWT auth claims.
    """
    return _get_ref_data(tickers=tickers, fields=fields, desk=desk, ctx=ctx)


@mcp.tool()
def get_history(
    ticker: str,
    start_date: date,
    end_date: date,
    desk: DeskId,
    ctx: Context,
    frequency: Literal["daily", "weekly", "monthly"] = "daily",
) -> dict:
    """
    Fetch historical price and volatility time series for a single security.

    Returns OHLCV bars plus rolling 30-day realised vol and implied vol for
    each period.

    USE THIS FOR:
      - Backtesting lookback windows (realised vol, VWAP, price returns)
      - Term-structure analysis for vol surface construction
      - Historical implied vol vs. realised vol spread (vol premium)
      - Earnings drift analysis (compare price path around EARN_ANNOUNCE_DT)
      - Index / futures basis tracking over time

    DO NOT USE FOR:
      - Greeks P&L attribution — use calculate_risk with position context
      - Forward-looking scenario generation — use run_scenario
      - Cross-asset correlation matrices — use calculate_risk(metric="correlation")
      - Real-time streaming data — this is bar/snapshot data only

    Args:
        ticker:     Bloomberg ticker, e.g. "AAPL US Equity".
        start_date: First bar date (ISO 8601).
        end_date:   Last bar date (ISO 8601).  Must be >= start_date.
        desk:       Calling PM's trading desk.
        ctx:        MCP context carrying JWT auth claims.
        frequency:  Bar frequency: "daily" (default), "weekly", or "monthly".
    """
    return _get_history(
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        desk=desk,
        ctx=ctx,
        frequency=frequency,
    )


@mcp.tool()
def search_securities(
    query: str,
    ctx: Context,
    asset_class: Optional[Literal["equity", "option", "future", "bond"]] = None,
) -> dict:
    """
    Search the Bloomberg security universe by keyword.

    Performs case-insensitive substring matching against ticker symbols,
    short tickers, and security names.

    USE THIS FOR:
      - Discovering the exact Bloomberg ticker format required by other tools
      - Listing available securities in a given asset class
      - Validating that a ticker exists before building a basket request
      - Finding option contracts on a given underlying

    DO NOT USE FOR:
      - Fetching price or vol data — use get_ref_data
      - Fetching historical time series — use get_history
      - Searching news or research reports — use search_research
      - Screening by fundamental criteria — use get_ref_data and filter client-side

    Args:
        query:       Search string matched against ticker, short_ticker, name.
                     Examples: "AAPL", "apple", "SPX", "VIX", "jan 2025"
        ctx:         MCP context carrying JWT auth claims.
        asset_class: Optional filter: "equity", "option", "future", or "bond".
    """
    return _search_securities(query=query, ctx=ctx, asset_class=asset_class)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("bloomberg_mcp_starting", port=8010)
    import os
    os.environ.setdefault("MCP_HTTP_HOST", "0.0.0.0")
    os.environ.setdefault("MCP_HTTP_PORT", "8010")
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
