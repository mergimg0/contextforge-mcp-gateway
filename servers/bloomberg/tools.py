"""
Bloomberg MCP tool implementations.

All tools require a valid JWT with the 'bloomberg:read' scope and
enforce PM desk isolation via DeskIsolation.enforce().

Negative-instruction conventions used throughout:
  - These tools surface market data only.
  - Do NOT use them for risk metrics (delta, gamma, VaR) — use calculate_risk.
  - Do NOT use them for portfolio positions — use get_positions.
  - Do NOT use them for scenario analysis — use run_scenario.
"""

from __future__ import annotations

import sys
import os
from datetime import date
from typing import Literal, Optional

# Allow running from project root with PYTHONPATH=/app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import structlog
from mcp.server.fastmcp import Context

from shared.isolation import DeskIsolation
from shared.models import DeskId

from .data import SECURITIES, ALL_KNOWN_FIELDS, generate_history
from .data import search_securities as _search_securities

log = structlog.get_logger("bloomberg.tools")


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

    Returns:
        {
          "data": {
            "<ticker>": {"<field>": <value>, ...},
            ...
          },
          "meta": {
            "tickers_requested": N,
            "tickers_found": M,
            "fields_requested": K,
            "unknown_fields": [...],
            "subject": "<pm-subject>",
            "desk": "<desk>"
          }
        }
    """
    subject, desk_access = DeskIsolation.enforce(ctx, desk, "get_ref_data")

    if len(tickers) > 50:
        from mcp import McpError
        from mcp.types import ErrorCode
        raise McpError(
            ErrorCode.INVALID_PARAMS,
            f"Too many tickers: {len(tickers)} (max 50 per request)",
        )

    unknown_fields = [f for f in fields if f not in ALL_KNOWN_FIELDS]

    result_data: dict[str, dict] = {}
    tickers_found = 0

    for ticker in tickers:
        sec = SECURITIES.get(ticker)
        if sec is None:
            # Return nulls for unknown tickers so the caller can tell what
            # was not found without raising a hard error.
            result_data[ticker] = {field: None for field in fields}
            result_data[ticker]["_error"] = f"Ticker not found: {ticker}"
            continue

        tickers_found += 1
        ticker_data: dict = {}
        for field in fields:
            ticker_data[field] = sec.get(field)  # None if field not present
        result_data[ticker] = ticker_data

    log.info(
        "get_ref_data",
        subject=subject,
        desk=desk,
        tickers_count=len(tickers),
        tickers_found=tickers_found,
        fields_count=len(fields),
    )

    return {
        "data": result_data,
        "meta": {
            "tickers_requested": len(tickers),
            "tickers_found": tickers_found,
            "fields_requested": len(fields),
            "unknown_fields": unknown_fields,
            "subject": subject,
            "desk": desk,
        },
    }


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
    each period.  Data is synthetic but generated from a calibrated GBM/OU
    model anchored to the security's current reference data values.

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
                    Daily bars skip weekends.

    Returns:
        {
          "ticker": "<ticker>",
          "frequency": "<frequency>",
          "bars": [
            {
              "date": "YYYY-MM-DD",
              "PX_OPEN": ..., "PX_HIGH": ..., "PX_LOW": ..., "PX_LAST": ...,
              "VOLUME": ...,
              "HIST_REALIZED_VOL_30D": ...,
              "IMPLIED_VOL_30D": ...
            },
            ...
          ],
          "meta": {
            "bar_count": N,
            "subject": "<pm-subject>",
            "desk": "<desk>"
          }
        }
    """
    subject, desk_access = DeskIsolation.enforce(ctx, desk, "get_history")

    if start_date > end_date:
        from mcp import McpError
        from mcp.types import ErrorCode
        raise McpError(
            ErrorCode.INVALID_PARAMS,
            f"start_date ({start_date}) must be <= end_date ({end_date})",
        )

    # Enforce reasonable lookback ceiling to prevent runaway generation
    from datetime import timedelta
    max_span_days = 3 * 365
    if (end_date - start_date).days > max_span_days:
        from mcp import McpError
        from mcp.types import ErrorCode
        raise McpError(
            ErrorCode.INVALID_PARAMS,
            f"Date range too large (max {max_span_days} days). "
            "Use a narrower window or increase frequency to 'weekly'/'monthly'.",
        )

    if ticker not in SECURITIES:
        from mcp import McpError
        from mcp.types import ErrorCode
        raise McpError(
            ErrorCode.INVALID_PARAMS,
            f"Ticker not found: '{ticker}'. Use search_securities to discover valid tickers.",
        )

    bars = generate_history(ticker, start_date, end_date, frequency)

    log.info(
        "get_history",
        subject=subject,
        desk=desk,
        ticker=ticker,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        frequency=frequency,
        bar_count=len(bars),
    )

    return {
        "ticker": ticker,
        "frequency": frequency,
        "bars": bars,
        "meta": {
            "bar_count": len(bars),
            "subject": subject,
            "desk": desk,
        },
    }


def search_securities(
    query: str,
    ctx: Context,
    asset_class: Optional[Literal["equity", "option", "future", "bond"]] = None,
) -> dict:
    """
    Search the Bloomberg security universe by keyword.

    Performs case-insensitive substring matching against ticker symbols,
    short tickers, and security names.  Returns lightweight summary records
    suitable for ticker discovery before calling get_ref_data or get_history.

    USE THIS FOR:
      - Discovering the exact Bloomberg ticker format required by other tools
        (e.g. "AAPL US Equity" vs. "AAPL US 01/17/25 C190 Equity")
      - Listing available securities in a given asset class
      - Validating that a ticker exists before building a basket request
      - Finding option contracts on a given underlying (query by underlying
        ticker, filter by asset_class="option")

    DO NOT USE FOR:
      - Fetching price or vol data — use get_ref_data
      - Fetching historical time series — use get_history
      - Searching news or research reports — use search_research
      - Screening by fundamental criteria (P/E, market cap) — use get_ref_data
        with a known ticker list and filter client-side

    NOTE: This mock universe contains ~15 representative securities.
    Production Bloomberg would return thousands of matches; design workflows
    that tolerate larger result sets.

    Args:
        query:       Search string.  Matched as case-insensitive substring
                     against ticker, short_ticker, and name fields.
                     Examples: "AAPL", "apple", "SPX", "VIX", "jan 2025"
        ctx:         MCP context carrying JWT auth claims.
        asset_class: Optional filter.  One of "equity", "option", "future",
                     "bond".  Omit to search all asset classes.

    Returns:
        {
          "results": [
            {
              "ticker": "AAPL US Equity",
              "name": "Apple Inc",
              "asset_class": "equity",
              "PX_LAST": 189.30,
              "CRNCY": "USD"
            },
            ...
          ],
          "meta": {
            "query": "<query>",
            "asset_class_filter": "<filter or null>",
            "result_count": N
          }
        }
    """
    # search_securities does not gate on desk — it's a discovery tool that
    # reveals no non-public information.  We still extract the subject for
    # audit purposes but do not call DeskIsolation.enforce().
    claims = ctx.auth or {}
    subject = claims.get("sub", "unknown")

    if not query or not query.strip():
        from mcp import McpError
        from mcp.types import ErrorCode
        raise McpError(
            ErrorCode.INVALID_PARAMS,
            "query must be a non-empty string.",
        )

    results = _search_securities(query.strip(), asset_class=asset_class)

    log.info(
        "search_securities",
        subject=subject,
        query=query,
        asset_class_filter=asset_class,
        result_count=len(results),
    )

    return {
        "results": results,
        "meta": {
            "query": query,
            "asset_class_filter": asset_class,
            "result_count": len(results),
        },
    }
