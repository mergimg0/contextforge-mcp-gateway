"""
Pre-built validation plan templates for each ClaimType.

Each template is a list of ToolCallGroup definitions with placeholder tokens
that get substituted by PlanGenerator:
  {asset}  → e.g. "AAPL US Equity"
  {desk}   → e.g. "vol"
  {ticker_bloomberg} → Bloomberg-format ticker

Templates are kept here as pure data so they can be overridden via the
plan_templates.yaml config without changing code.
"""

from __future__ import annotations

from typing import Callable

from ..parser.models import ClaimType
from .models import ToolCallGroup, ToolCallSpec

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _group(name: str, calls: list[ToolCallSpec], dependencies: list[str] | None = None, description: str = "") -> ToolCallGroup:
    return ToolCallGroup.model_validate({
        "name": name,
        "calls": [c.model_dump() for c in calls],
        "dependencies": dependencies or [],
        "description": description,
    })


# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------

def vol_mispricing_template(asset: str, desk: str) -> list[ToolCallGroup]:
    """
    Vol-mispricing validation:
      Group 1 (parallel): IV/RV snapshot + 90-day history + event calendar
      Group 2 (after 1): Option Greeks + vol scenario P&L
      Group 3 (after 2): Research note for context
    """
    bloomberg_ticker = f"{asset} US Equity" if " " not in asset else asset

    return [
        _group(
            name="market_data",
            description="Fetch current vol snapshot, 90-day IV/RV history, and event calendar",
            calls=[
                ToolCallSpec(
                    server="bloomberg",
                    tool="get_ref_data",
                    arguments={
                        "tickers": [bloomberg_ticker],
                        "fields": [
                            "PX_LAST",
                            "IMPLIED_VOL_30D",
                            "HIST_REALIZED_VOL_30D",
                            "EARN_ANNOUNCE_DT",
                        ],
                        "desk": desk,
                    },
                    purpose="Snapshot of current IV, RV, and next earnings date for IV-RV spread assessment",
                ),
                ToolCallSpec(
                    server="bloomberg",
                    tool="get_history",
                    arguments={
                        "ticker": bloomberg_ticker,
                        "start_date": "{{date_minus_90d}}",
                        "end_date": "{{date_today}}",
                        "desk": desk,
                        "frequency": "daily",
                    },
                    purpose="90-day IV and RV history to compute rolling IV-RV spread and percentile rank",
                ),
            ],
        ),
        _group(
            name="risk_analysis",
            description="Greeks aggregation and vol-spike scenario to quantify P&L risk",
            dependencies=["market_data"],
            calls=[
                ToolCallSpec(
                    server="risk",
                    tool="get_greeks",
                    arguments={
                        "query": {
                            "desk": desk,
                            "underlying": asset,
                        }
                    },
                    purpose="Portfolio vega/gamma exposure to understand existing vol position before adding",
                ),
                ToolCallSpec(
                    server="risk",
                    tool="run_scenario",
                    arguments={
                        "params": {
                            "desk": desk,
                            "scenario": "vol_spike",
                            "magnitude": 2.0,
                        }
                    },
                    purpose="Stress-test a 2x vol-spike to bound downside if IV mispricing widens further",
                ),
            ],
        ),
        _group(
            name="research_context",
            description="Analyst research for fundamental context on vol catalyst",
            dependencies=["market_data"],
            calls=[
                ToolCallSpec(
                    server="research",
                    tool="search_research",
                    arguments={"query": f"{asset} volatility options catalyst", "max_results": 3},
                    purpose="Recent analyst commentary on vol catalysts and event risk",
                    required=False,
                ),
            ],
        ),
    ]


def momentum_template(asset: str, desk: str) -> list[ToolCallGroup]:
    """
    Momentum validation:
      Group 1 (parallel): Price history (90d) + sector comparison
      Group 2 (after 1): VaR + research sector analysis
    """
    bloomberg_ticker = f"{asset} US Equity" if " " not in asset else asset
    # Derive sector proxy — simplistic mapping used for demo
    sector_index = _sector_index_for(asset)

    return [
        _group(
            name="market_data",
            description="Price and momentum indicator history for signal confirmation",
            calls=[
                ToolCallSpec(
                    server="bloomberg",
                    tool="get_history",
                    arguments={
                        "ticker": bloomberg_ticker,
                        "start_date": "{{date_minus_90d}}",
                        "end_date": "{{date_today}}",
                        "desk": desk,
                        "frequency": "daily",
                    },
                    purpose="90-day price history to compute momentum, RSI, and trend strength",
                ),
                ToolCallSpec(
                    server="bloomberg",
                    tool="get_history",
                    arguments={
                        "ticker": sector_index,
                        "start_date": "{{date_minus_90d}}",
                        "end_date": "{{date_today}}",
                        "desk": desk,
                        "frequency": "daily",
                    },
                    purpose=f"Sector benchmark ({sector_index}) history for relative momentum divergence analysis",
                    required=False,
                ),
                ToolCallSpec(
                    server="bloomberg",
                    tool="get_ref_data",
                    arguments={
                        "tickers": [bloomberg_ticker],
                        "fields": ["PX_LAST", "VOLUME", "PE_RATIO", "HIST_REALIZED_VOL_30D"],
                        "desk": desk,
                    },
                    purpose="Current price, volume, and valuation snapshot for momentum context",
                ),
            ],
        ),
        _group(
            name="risk_analysis",
            description="VaR to size position and scenario for momentum reversal risk",
            dependencies=["market_data"],
            calls=[
                ToolCallSpec(
                    server="risk",
                    tool="calculate_var",
                    arguments={
                        "query": {
                            "desk": desk,
                            "metric": "var",
                            "confidence": 0.99,
                            "horizon_days": 5,
                        }
                    },
                    purpose="5-day 99% VaR to size the momentum position within risk limits",
                ),
                ToolCallSpec(
                    server="risk",
                    tool="run_scenario",
                    arguments={
                        "params": {
                            "desk": desk,
                            "scenario": "equity_crash",
                            "magnitude": 1.5,
                        }
                    },
                    purpose="Equity-crash scenario to bound loss if momentum reverses sharply",
                ),
            ],
        ),
        _group(
            name="research_context",
            description="Sector research and analyst views for momentum confirmation",
            dependencies=["market_data"],
            calls=[
                ToolCallSpec(
                    server="research",
                    tool="search_research",
                    arguments={"query": f"{asset} momentum technical sector outlook", "max_results": 3},
                    purpose="Analyst notes on sector momentum and technical setup",
                    required=False,
                ),
            ],
        ),
    ]


def relative_value_template(asset: str, desk: str) -> list[ToolCallGroup]:
    """
    Relative-value validation:
      Group 1 (parallel): Spread/price history + comparator data
      Group 2 (after 1): Scenario analysis for spread widening/tightening
      Group 3 (after 1): Research on spread drivers
    """
    bloomberg_ticker = f"{asset} US Equity" if " " not in asset else asset

    return [
        _group(
            name="market_data",
            description="Historical spread and relative price data for percentile ranking",
            calls=[
                ToolCallSpec(
                    server="bloomberg",
                    tool="get_ref_data",
                    arguments={
                        "tickers": [bloomberg_ticker],
                        "fields": [
                            "PX_LAST",
                            "PE_RATIO",
                            "HIST_REALIZED_VOL_30D",
                            "EQY_WEIGHTED_AVG_PX",
                        ],
                        "desk": desk,
                    },
                    purpose="Current price and valuation ratios vs. historical averages",
                ),
                ToolCallSpec(
                    server="bloomberg",
                    tool="get_history",
                    arguments={
                        "ticker": bloomberg_ticker,
                        "start_date": "{{date_minus_252d}}",
                        "end_date": "{{date_today}}",
                        "desk": desk,
                        "frequency": "weekly",
                    },
                    purpose="1-year weekly history to compute z-score and percentile rank of current spread",
                ),
            ],
        ),
        _group(
            name="risk_analysis",
            description="Scenario analysis for spread convergence / divergence paths",
            dependencies=["market_data"],
            calls=[
                ToolCallSpec(
                    server="risk",
                    tool="run_scenario",
                    arguments={
                        "params": {
                            "desk": desk,
                            "scenario": "custom",
                            "magnitude": 2.0,
                        }
                    },
                    purpose="Custom stress to model impact if spread continues to diverge rather than converge",
                ),
                ToolCallSpec(
                    server="risk",
                    tool="calculate_var",
                    arguments={
                        "query": {
                            "desk": desk,
                            "metric": "cvar",
                            "confidence": 0.95,
                            "horizon_days": 10,
                        }
                    },
                    purpose="10-day CVaR to understand tail risk of the relative value position",
                ),
            ],
        ),
        _group(
            name="research_context",
            description="Fundamental research on spread drivers and reversion triggers",
            dependencies=["market_data"],
            calls=[
                ToolCallSpec(
                    server="research",
                    tool="search_research",
                    arguments={"query": f"{asset} relative value spread catalyst fundamental", "max_results": 3},
                    purpose="Analyst research on fundamental drivers and catalysts for spread convergence",
                    required=False,
                ),
            ],
        ),
    ]


def mean_reversion_template(asset: str, desk: str) -> list[ToolCallGroup]:
    """
    Mean-reversion validation:
      Group 1: Spread/price history to compute z-score vs. mean
      Group 2: Scenario for further deviation + CVaR
      Group 3: Research on mean-reversion anchor
    """
    bloomberg_ticker = f"{asset} US Equity" if " " not in asset else asset

    return [
        _group(
            name="market_data",
            description="Long-dated history to establish mean and measure current deviation",
            calls=[
                ToolCallSpec(
                    server="bloomberg",
                    tool="get_history",
                    arguments={
                        "ticker": bloomberg_ticker,
                        "start_date": "{{date_minus_252d}}",
                        "end_date": "{{date_today}}",
                        "desk": desk,
                        "frequency": "weekly",
                    },
                    purpose="1-year weekly history to establish statistical mean and measure current deviation (z-score)",
                ),
                ToolCallSpec(
                    server="bloomberg",
                    tool="get_ref_data",
                    arguments={
                        "tickers": [bloomberg_ticker],
                        "fields": ["PX_LAST", "PE_RATIO", "HIST_REALIZED_VOL_30D"],
                        "desk": desk,
                    },
                    purpose="Current snapshot to compare against long-run mean",
                ),
            ],
        ),
        _group(
            name="risk_analysis",
            description="Bound downside if mean-reversion is delayed or reverses",
            dependencies=["market_data"],
            calls=[
                ToolCallSpec(
                    server="risk",
                    tool="calculate_var",
                    arguments={
                        "query": {
                            "desk": desk,
                            "metric": "cvar",
                            "confidence": 0.95,
                            "horizon_days": 10,
                        }
                    },
                    purpose="CVaR tail risk if mean-reversion stalls and position moves against thesis",
                ),
                ToolCallSpec(
                    server="risk",
                    tool="run_scenario",
                    arguments={
                        "params": {
                            "desk": desk,
                            "scenario": "custom",
                            "magnitude": 3.0,
                        }
                    },
                    purpose="Extreme-stress scenario: what if deviation extends a further 3 sigma?",
                ),
            ],
        ),
        _group(
            name="research_context",
            description="Research on what drives reversion to mean in this instrument",
            dependencies=["market_data"],
            calls=[
                ToolCallSpec(
                    server="research",
                    tool="search_research",
                    arguments={"query": f"{asset} mean reversion fundamental anchor valuation", "max_results": 3},
                    purpose="Analyst views on fundamental anchors and reversion catalysts",
                    required=False,
                ),
            ],
        ),
    ]


def event_driven_template(asset: str, desk: str) -> list[ToolCallGroup]:
    """
    Event-driven validation:
      Group 1: Event calendar + implied move + price history
      Group 2: Greeks pre-event + event scenario
      Group 3: Analyst estimates and event research
    """
    bloomberg_ticker = f"{asset} US Equity" if " " not in asset else asset

    return [
        _group(
            name="market_data",
            description="Event date, implied move from straddle pricing, and pre-event price history",
            calls=[
                ToolCallSpec(
                    server="bloomberg",
                    tool="get_ref_data",
                    arguments={
                        "tickers": [bloomberg_ticker],
                        "fields": [
                            "EARN_ANNOUNCE_DT",
                            "IMPLIED_VOL_30D",
                            "HIST_REALIZED_VOL_30D",
                            "PX_LAST",
                            "DVD_YILD",
                        ],
                        "desk": desk,
                    },
                    purpose="Event date and current ATM implied vol (proxy for expected move) for event risk quantification",
                ),
                ToolCallSpec(
                    server="bloomberg",
                    tool="get_history",
                    arguments={
                        "ticker": bloomberg_ticker,
                        "start_date": "{{date_minus_90d}}",
                        "end_date": "{{date_today}}",
                        "desk": desk,
                        "frequency": "daily",
                    },
                    purpose="Pre-event price history to compare current vol to prior earnings implied moves",
                ),
            ],
        ),
        _group(
            name="risk_analysis",
            description="Greeks and event-shock scenario to bound P&L around the catalyst",
            dependencies=["market_data"],
            calls=[
                ToolCallSpec(
                    server="risk",
                    tool="get_greeks",
                    arguments={
                        "query": {
                            "desk": desk,
                            "underlying": asset,
                        }
                    },
                    purpose="Current delta/gamma/vega exposure to understand event sensitivity of existing book",
                ),
                ToolCallSpec(
                    server="risk",
                    tool="run_scenario",
                    arguments={
                        "params": {
                            "desk": desk,
                            "scenario": "equity_crash",
                            "magnitude": 2.0,
                        }
                    },
                    purpose="Downside scenario if event outcome is negative (2x normal equity crash severity)",
                ),
            ],
        ),
        _group(
            name="research_context",
            description="Analyst estimates and historical event-study research",
            dependencies=["market_data"],
            calls=[
                ToolCallSpec(
                    server="research",
                    tool="search_research",
                    arguments={"query": f"{asset} earnings estimates catalyst event", "max_results": 3},
                    purpose="Analyst estimates and event-study analysis for earnings catalyst",
                    required=False,
                ),
            ],
        ),
    ]


def macro_template(asset: str, desk: str) -> list[ToolCallGroup]:
    """
    Macro validation:
      Group 1: Multi-asset snapshot + yield curve / FX history
      Group 2: Rate-shock scenario + VaR
      Group 3: Macro research
    """
    bloomberg_ticker = f"{asset} US Equity" if " " not in asset else asset

    return [
        _group(
            name="market_data",
            description="Macro factor history and cross-asset snapshot",
            calls=[
                ToolCallSpec(
                    server="bloomberg",
                    tool="get_history",
                    arguments={
                        "ticker": bloomberg_ticker,
                        "start_date": "{{date_minus_252d}}",
                        "end_date": "{{date_today}}",
                        "desk": desk,
                        "frequency": "weekly",
                    },
                    purpose="1-year weekly history of primary macro instrument to establish trend and deviation",
                ),
                ToolCallSpec(
                    server="bloomberg",
                    tool="get_ref_data",
                    arguments={
                        "tickers": [bloomberg_ticker, "SPX Index"],
                        "fields": ["PX_LAST", "HIST_REALIZED_VOL_30D", "IMPLIED_VOL_30D"],
                        "desk": desk,
                    },
                    purpose="Cross-asset snapshot to assess macro regime and correlation breakdown",
                ),
            ],
        ),
        _group(
            name="risk_analysis",
            description="Rate and macro stress scenarios to quantify portfolio sensitivity",
            dependencies=["market_data"],
            calls=[
                ToolCallSpec(
                    server="risk",
                    tool="run_scenario",
                    arguments={
                        "params": {
                            "desk": desk,
                            "scenario": "rate_shock",
                            "magnitude": 2.0,
                        }
                    },
                    purpose="Rate-shock stress (2x +100bps shift) to quantify portfolio duration and convexity exposure",
                ),
                ToolCallSpec(
                    server="risk",
                    tool="calculate_var",
                    arguments={
                        "query": {
                            "desk": desk,
                            "metric": "var",
                            "confidence": 0.99,
                            "horizon_days": 10,
                        }
                    },
                    purpose="10-day 99% VaR for macro position sizing against risk limits",
                ),
            ],
        ),
        _group(
            name="research_context",
            description="Macro research and central bank analysis",
            dependencies=["market_data"],
            calls=[
                ToolCallSpec(
                    server="research",
                    tool="search_research",
                    arguments={"query": f"{asset} macro monetary policy rate differential", "max_results": 3},
                    purpose="Macro research on rate differentials, central bank policy and FX dynamics",
                    required=False,
                ),
            ],
        ),
    ]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

TEMPLATES: dict[ClaimType, Callable[..., list[ToolCallGroup]]] = {
    ClaimType.VOL_MISPRICING: vol_mispricing_template,
    ClaimType.MOMENTUM: momentum_template,
    ClaimType.RELATIVE_VALUE: relative_value_template,
    ClaimType.MEAN_REVERSION: mean_reversion_template,
    ClaimType.EVENT_DRIVEN: event_driven_template,
    ClaimType.MACRO: macro_template,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sector_index_for(asset: str) -> str:
    """Return the relevant sector ETF or index for a given equity ticker."""
    tech = {"AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META"}
    financials = {"JPM", "GS", "MS", "BAC", "C", "WFC"}
    if asset in tech:
        return "XLK US Equity"
    if asset in financials:
        return "XLF US Equity"
    return "SPX Index"
