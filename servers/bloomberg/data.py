"""
Mock Bloomberg data for the ContextForge Bloomberg MCP server.

Provides realistic reference data, historical time series, and a security
universe using authentic Bloomberg field names. All values are synthetic
but calibrated to plausible ranges for an options/vol trading fund.
"""

from __future__ import annotations

import math
import random
from datetime import date, timedelta
from typing import Optional

# ---------------------------------------------------------------------------
# Security universe
# ---------------------------------------------------------------------------

SECURITIES: dict[str, dict] = {
    # ---- Large-cap equities ------------------------------------------------
    "AAPL US Equity": {
        "ticker": "AAPL US Equity",
        "short_ticker": "AAPL",
        "name": "Apple Inc",
        "asset_class": "equity",
        "GICS_SECTOR_NAME": "Information Technology",
        "PX_LAST": 189.30,
        "PX_OPEN": 188.10,
        "PX_HIGH": 190.45,
        "PX_LOW": 187.60,
        "VOLUME": 55_432_100,
        "IMPLIED_VOL_30D": 0.2215,
        "HIST_REALIZED_VOL_30D": 0.1980,
        "CUR_MKT_CAP": 2_920_000_000_000.0,
        "EQY_WEIGHTED_AVG_PX": 188.74,
        "EARN_ANNOUNCE_DT": "2025-01-30",
        "CRNCY": "USD",
        "EQY_FLOAT": 15_280_000_000,
        "DVD_YILD": 0.0053,
        "PE_RATIO": 31.2,
    },
    "MSFT US Equity": {
        "ticker": "MSFT US Equity",
        "short_ticker": "MSFT",
        "name": "Microsoft Corp",
        "asset_class": "equity",
        "GICS_SECTOR_NAME": "Information Technology",
        "PX_LAST": 415.80,
        "PX_OPEN": 413.20,
        "PX_HIGH": 417.55,
        "PX_LOW": 412.40,
        "VOLUME": 21_876_400,
        "IMPLIED_VOL_30D": 0.1985,
        "HIST_REALIZED_VOL_30D": 0.1762,
        "CUR_MKT_CAP": 3_090_000_000_000.0,
        "EQY_WEIGHTED_AVG_PX": 414.91,
        "EARN_ANNOUNCE_DT": "2025-01-29",
        "CRNCY": "USD",
        "EQY_FLOAT": 7_430_000_000,
        "DVD_YILD": 0.0072,
        "PE_RATIO": 36.8,
    },
    "GOOGL US Equity": {
        "ticker": "GOOGL US Equity",
        "short_ticker": "GOOGL",
        "name": "Alphabet Inc",
        "asset_class": "equity",
        "GICS_SECTOR_NAME": "Communication Services",
        "PX_LAST": 172.45,
        "PX_OPEN": 171.10,
        "PX_HIGH": 173.20,
        "PX_LOW": 170.55,
        "VOLUME": 24_310_000,
        "IMPLIED_VOL_30D": 0.2340,
        "HIST_REALIZED_VOL_30D": 0.2105,
        "CUR_MKT_CAP": 2_150_000_000_000.0,
        "EQY_WEIGHTED_AVG_PX": 171.83,
        "EARN_ANNOUNCE_DT": "2025-02-04",
        "CRNCY": "USD",
        "EQY_FLOAT": 12_380_000_000,
        "DVD_YILD": 0.0000,
        "PE_RATIO": 24.6,
    },
    "NVDA US Equity": {
        "ticker": "NVDA US Equity",
        "short_ticker": "NVDA",
        "name": "NVIDIA Corp",
        "asset_class": "equity",
        "GICS_SECTOR_NAME": "Information Technology",
        "PX_LAST": 875.40,
        "PX_OPEN": 862.15,
        "PX_HIGH": 881.30,
        "PX_LOW": 860.05,
        "VOLUME": 43_218_900,
        "IMPLIED_VOL_30D": 0.4820,
        "HIST_REALIZED_VOL_30D": 0.5140,
        "CUR_MKT_CAP": 2_150_000_000_000.0,
        "EQY_WEIGHTED_AVG_PX": 869.77,
        "EARN_ANNOUNCE_DT": "2025-02-26",
        "CRNCY": "USD",
        "EQY_FLOAT": 2_450_000_000,
        "DVD_YILD": 0.0004,
        "PE_RATIO": 65.3,
    },
    "META US Equity": {
        "ticker": "META US Equity",
        "short_ticker": "META",
        "name": "Meta Platforms Inc",
        "asset_class": "equity",
        "GICS_SECTOR_NAME": "Communication Services",
        "PX_LAST": 512.90,
        "PX_OPEN": 509.45,
        "PX_HIGH": 515.20,
        "PX_LOW": 507.80,
        "VOLUME": 18_654_200,
        "IMPLIED_VOL_30D": 0.3105,
        "HIST_REALIZED_VOL_30D": 0.2880,
        "CUR_MKT_CAP": 1_310_000_000_000.0,
        "EQY_WEIGHTED_AVG_PX": 511.44,
        "EARN_ANNOUNCE_DT": "2025-01-29",
        "CRNCY": "USD",
        "EQY_FLOAT": 2_550_000_000,
        "DVD_YILD": 0.0000,
        "PE_RATIO": 29.1,
    },
    "AMZN US Equity": {
        "ticker": "AMZN US Equity",
        "short_ticker": "AMZN",
        "name": "Amazon.com Inc",
        "asset_class": "equity",
        "GICS_SECTOR_NAME": "Consumer Discretionary",
        "PX_LAST": 198.25,
        "PX_OPEN": 196.80,
        "PX_HIGH": 199.60,
        "PX_LOW": 195.70,
        "VOLUME": 38_127_500,
        "IMPLIED_VOL_30D": 0.2590,
        "HIST_REALIZED_VOL_30D": 0.2310,
        "CUR_MKT_CAP": 2_080_000_000_000.0,
        "EQY_WEIGHTED_AVG_PX": 197.43,
        "EARN_ANNOUNCE_DT": "2025-02-06",
        "CRNCY": "USD",
        "EQY_FLOAT": 10_430_000_000,
        "DVD_YILD": 0.0000,
        "PE_RATIO": 42.5,
    },
    "GS US Equity": {
        "ticker": "GS US Equity",
        "short_ticker": "GS",
        "name": "Goldman Sachs Group Inc",
        "asset_class": "equity",
        "GICS_SECTOR_NAME": "Financials",
        "PX_LAST": 548.70,
        "PX_OPEN": 545.20,
        "PX_HIGH": 551.40,
        "PX_LOW": 543.85,
        "VOLUME": 1_985_300,
        "IMPLIED_VOL_30D": 0.2240,
        "HIST_REALIZED_VOL_30D": 0.2015,
        "CUR_MKT_CAP": 178_500_000_000.0,
        "EQY_WEIGHTED_AVG_PX": 547.33,
        "EARN_ANNOUNCE_DT": "2025-01-15",
        "CRNCY": "USD",
        "EQY_FLOAT": 325_000_000,
        "DVD_YILD": 0.0241,
        "PE_RATIO": 14.8,
    },
    # ---- Indices -----------------------------------------------------------
    "SPX Index": {
        "ticker": "SPX Index",
        "short_ticker": "SPX",
        "name": "S&P 500 Index",
        "asset_class": "equity",
        "GICS_SECTOR_NAME": None,
        "PX_LAST": 5_642.10,
        "PX_OPEN": 5_628.40,
        "PX_HIGH": 5_658.30,
        "PX_LOW": 5_620.75,
        "VOLUME": 3_421_560_000,
        "IMPLIED_VOL_30D": 0.1523,  # VIX implied
        "HIST_REALIZED_VOL_30D": 0.1284,
        "CUR_MKT_CAP": None,
        "EQY_WEIGHTED_AVG_PX": 5_635.22,
        "EARN_ANNOUNCE_DT": None,
        "CRNCY": "USD",
        "EQY_FLOAT": None,
        "DVD_YILD": 0.0134,
        "PE_RATIO": 21.4,
    },
    "NDX Index": {
        "ticker": "NDX Index",
        "short_ticker": "NDX",
        "name": "Nasdaq 100 Index",
        "asset_class": "equity",
        "GICS_SECTOR_NAME": None,
        "PX_LAST": 19_854.30,
        "PX_OPEN": 19_792.10,
        "PX_HIGH": 19_912.50,
        "PX_LOW": 19_768.40,
        "VOLUME": 890_432_000,
        "IMPLIED_VOL_30D": 0.1892,
        "HIST_REALIZED_VOL_30D": 0.1715,
        "CUR_MKT_CAP": None,
        "EQY_WEIGHTED_AVG_PX": 19_831.67,
        "EARN_ANNOUNCE_DT": None,
        "CRNCY": "USD",
        "EQY_FLOAT": None,
        "DVD_YILD": 0.0068,
        "PE_RATIO": 29.7,
    },
    "VIX Index": {
        "ticker": "VIX Index",
        "short_ticker": "VIX",
        "name": "CBOE Volatility Index",
        "asset_class": "equity",
        "GICS_SECTOR_NAME": None,
        "PX_LAST": 15.23,
        "PX_OPEN": 15.84,
        "PX_HIGH": 16.10,
        "PX_LOW": 14.98,
        "VOLUME": None,
        "IMPLIED_VOL_30D": None,
        "HIST_REALIZED_VOL_30D": None,
        "CUR_MKT_CAP": None,
        "EQY_WEIGHTED_AVG_PX": None,
        "EARN_ANNOUNCE_DT": None,
        "CRNCY": "USD",
        "EQY_FLOAT": None,
        "DVD_YILD": None,
        "PE_RATIO": None,
    },
    # ---- Equity options (representative contracts) -------------------------
    "AAPL US 01/17/25 C190 Equity": {
        "ticker": "AAPL US 01/17/25 C190 Equity",
        "short_ticker": "AAPL C190 Jan25",
        "name": "AAPL Jan 2025 190 Call",
        "asset_class": "option",
        "GICS_SECTOR_NAME": None,
        "PX_LAST": 4.85,
        "PX_OPEN": 4.60,
        "PX_HIGH": 5.10,
        "PX_LOW": 4.55,
        "VOLUME": 12_540,
        "IMPLIED_VOL_30D": 0.2415,
        "HIST_REALIZED_VOL_30D": 0.1980,
        "CUR_MKT_CAP": None,
        "EQY_WEIGHTED_AVG_PX": 4.78,
        "EARN_ANNOUNCE_DT": None,
        "CRNCY": "USD",
        "OPT_DELTA": 0.4820,
        "OPT_GAMMA": 0.0245,
        "OPT_VEGA": 0.2310,
        "OPT_THETA": -0.0842,
        "OPT_STRIKE_PX": 190.0,
        "OPT_EXPIRE_DT": "2025-01-17",
        "OPT_PUT_CALL": "Call",
        "UNDERLYING_TICKER": "AAPL US Equity",
        "EQY_FLOAT": None,
        "DVD_YILD": None,
        "PE_RATIO": None,
    },
    "SPX US 12/31/25 P5500 Index": {
        "ticker": "SPX US 12/31/25 P5500 Index",
        "short_ticker": "SPX P5500 Dec25",
        "name": "SPX Dec 2025 5500 Put",
        "asset_class": "option",
        "GICS_SECTOR_NAME": None,
        "PX_LAST": 98.40,
        "PX_OPEN": 96.10,
        "PX_HIGH": 100.20,
        "PX_LOW": 95.50,
        "VOLUME": 3_210,
        "IMPLIED_VOL_30D": 0.1648,
        "HIST_REALIZED_VOL_30D": 0.1284,
        "CUR_MKT_CAP": None,
        "EQY_WEIGHTED_AVG_PX": 97.83,
        "EARN_ANNOUNCE_DT": None,
        "CRNCY": "USD",
        "OPT_DELTA": -0.3150,
        "OPT_GAMMA": 0.0008,
        "OPT_VEGA": 7.842,
        "OPT_THETA": -1.243,
        "OPT_STRIKE_PX": 5500.0,
        "OPT_EXPIRE_DT": "2025-12-31",
        "OPT_PUT_CALL": "Put",
        "UNDERLYING_TICKER": "SPX Index",
        "EQY_FLOAT": None,
        "DVD_YILD": None,
        "PE_RATIO": None,
    },
    # ---- Futures -----------------------------------------------------------
    "ESZ5 Index": {
        "ticker": "ESZ5 Index",
        "short_ticker": "ESZ5",
        "name": "E-mini S&P 500 Dec 2025",
        "asset_class": "future",
        "GICS_SECTOR_NAME": None,
        "PX_LAST": 5_648.25,
        "PX_OPEN": 5_635.00,
        "PX_HIGH": 5_663.50,
        "PX_LOW": 5_628.75,
        "VOLUME": 1_243_800,
        "IMPLIED_VOL_30D": 0.1523,
        "HIST_REALIZED_VOL_30D": 0.1284,
        "CUR_MKT_CAP": None,
        "EQY_WEIGHTED_AVG_PX": 5_645.10,
        "EARN_ANNOUNCE_DT": None,
        "CRNCY": "USD",
        "FUT_EXPIRE_DT": "2025-12-19",
        "FUT_CONTRACT_SZ": 50,
        "EQY_FLOAT": None,
        "DVD_YILD": None,
        "PE_RATIO": None,
    },
    "VXZ5 Index": {
        "ticker": "VXZ5 Index",
        "short_ticker": "VXZ5",
        "name": "VIX Dec 2025 Futures",
        "asset_class": "future",
        "GICS_SECTOR_NAME": None,
        "PX_LAST": 18.45,
        "PX_OPEN": 18.20,
        "PX_HIGH": 18.70,
        "PX_LOW": 18.10,
        "VOLUME": 184_320,
        "IMPLIED_VOL_30D": None,
        "HIST_REALIZED_VOL_30D": None,
        "CUR_MKT_CAP": None,
        "EQY_WEIGHTED_AVG_PX": 18.38,
        "EARN_ANNOUNCE_DT": None,
        "CRNCY": "USD",
        "FUT_EXPIRE_DT": "2025-12-17",
        "FUT_CONTRACT_SZ": 1000,
        "EQY_FLOAT": None,
        "DVD_YILD": None,
        "PE_RATIO": None,
    },
    # ---- Corporate bond ----------------------------------------------------
    "AAPL 3.85 05/04/43 Corp": {
        "ticker": "AAPL 3.85 05/04/43 Corp",
        "short_ticker": "AAPL 43s",
        "name": "Apple Inc 3.85% 2043",
        "asset_class": "bond",
        "GICS_SECTOR_NAME": "Information Technology",
        "PX_LAST": 88.42,
        "PX_OPEN": 88.25,
        "PX_HIGH": 88.68,
        "PX_LOW": 88.10,
        "VOLUME": 24_500_000,
        "IMPLIED_VOL_30D": None,
        "HIST_REALIZED_VOL_30D": None,
        "CUR_MKT_CAP": None,
        "EQY_WEIGHTED_AVG_PX": 88.35,
        "EARN_ANNOUNCE_DT": None,
        "CRNCY": "USD",
        "YLD_YTM_MID": 0.0512,
        "DUR_ADJ_OAS_BPS": 112.4,
        "MATURITY": "2043-05-04",
        "CPN": 3.85,
        "RTG_MOODY": "Aaa",
        "RTG_SP": "AAA",
        "EQY_FLOAT": None,
        "DVD_YILD": None,
        "PE_RATIO": None,
    },
}

# Canonical field names known to this server
ALL_KNOWN_FIELDS = {
    "PX_LAST", "PX_OPEN", "PX_HIGH", "PX_LOW", "VOLUME",
    "IMPLIED_VOL_30D", "HIST_REALIZED_VOL_30D", "CUR_MKT_CAP",
    "EQY_WEIGHTED_AVG_PX", "EARN_ANNOUNCE_DT", "CRNCY",
    "EQY_FLOAT", "DVD_YILD", "PE_RATIO", "GICS_SECTOR_NAME",
    "OPT_DELTA", "OPT_GAMMA", "OPT_VEGA", "OPT_THETA",
    "OPT_STRIKE_PX", "OPT_EXPIRE_DT", "OPT_PUT_CALL",
    "UNDERLYING_TICKER", "FUT_EXPIRE_DT", "FUT_CONTRACT_SZ",
    "YLD_YTM_MID", "DUR_ADJ_OAS_BPS", "MATURITY", "CPN",
    "RTG_MOODY", "RTG_SP",
}


# ---------------------------------------------------------------------------
# History generation
# ---------------------------------------------------------------------------

def generate_history(
    ticker: str,
    start_date: date,
    end_date: date,
    frequency: str = "daily",
) -> list[dict]:
    """
    Generate a plausible OHLCV + vol time series for a given ticker.

    Uses a geometric Brownian motion with calibrated drift and vol drawn
    from the security's HIST_REALIZED_VOL_30D.  Vol itself is mean-reverting
    (Ornstein-Uhlenbeck) around the security's IMPLIED_VOL_30D anchor.

    Args:
        ticker: Bloomberg ticker key in SECURITIES.
        start_date: First bar date (inclusive).
        end_date: Last bar date (inclusive).
        frequency: "daily" | "weekly" | "monthly"

    Returns:
        List of dicts with keys: date, PX_OPEN, PX_HIGH, PX_LOW, PX_LAST,
        VOLUME, HIST_REALIZED_VOL_30D (rolling, annualised).
    """
    sec = SECURITIES.get(ticker)
    if sec is None:
        return []

    base_price = sec.get("PX_LAST", 100.0) or 100.0
    base_vol = sec.get("HIST_REALIZED_VOL_30D", 0.20) or 0.20
    base_volume = sec.get("VOLUME", 1_000_000) or 1_000_000

    # Determine calendar stride
    if frequency == "weekly":
        delta = timedelta(weeks=1)
    elif frequency == "monthly":
        delta = timedelta(days=30)
    else:
        delta = timedelta(days=1)

    # Seed from ticker for reproducibility
    rng = random.Random(hash(ticker) & 0xFFFFFFFF)

    # Daily vol from annualised
    daily_vol = base_vol / math.sqrt(252)
    drift = 0.00008  # slight upward drift

    records = []
    price = base_price
    vol = base_vol
    current = start_date

    # Rolling window for realised vol calc (30 bars)
    returns_window: list[float] = []

    while current <= end_date:
        # Skip weekends for daily
        if frequency == "daily" and current.weekday() >= 5:
            current += delta
            continue

        # GBM step
        z = rng.gauss(0, 1)
        daily_ret = drift + daily_vol * z
        price_open = price
        price = price * math.exp(daily_ret)

        # Intraday range: proportional to vol
        intraday_spread = price * daily_vol * abs(rng.gauss(0, 1)) * 1.5
        px_high = max(price_open, price) + intraday_spread * 0.6
        px_low = min(price_open, price) - intraday_spread * 0.4

        # Volume noise
        vol_factor = rng.lognormvariate(0, 0.35)
        volume = int(base_volume * vol_factor)

        # Rolling realised vol (annualised)
        if len(returns_window) > 0:
            returns_window.append(daily_ret)
        else:
            returns_window.append(daily_ret)
        if len(returns_window) > 30:
            returns_window.pop(0)

        if len(returns_window) >= 2:
            mean_r = sum(returns_window) / len(returns_window)
            variance = sum((r - mean_r) ** 2 for r in returns_window) / (len(returns_window) - 1)
            realised_vol = math.sqrt(variance * 252)
        else:
            realised_vol = base_vol

        # Vol mean-reversion step (OU)
        vol = vol + 0.15 * (base_vol - vol) + 0.02 * rng.gauss(0, 1) * vol
        vol = max(0.05, min(vol, 2.0))

        records.append(
            {
                "date": current.isoformat(),
                "PX_OPEN": round(price_open, 4),
                "PX_HIGH": round(px_high, 4),
                "PX_LOW": round(max(px_low, 0.01), 4),
                "PX_LAST": round(price, 4),
                "VOLUME": volume,
                "HIST_REALIZED_VOL_30D": round(realised_vol, 6),
                "IMPLIED_VOL_30D": round(vol, 6),
            }
        )
        current += delta

    return records


# ---------------------------------------------------------------------------
# Security search
# ---------------------------------------------------------------------------

def search_securities(
    query: str,
    asset_class: Optional[str] = None,
) -> list[dict]:
    """
    Fuzzy-match securities against query string.

    Matches against ticker, short_ticker, and name (case-insensitive substring).
    Optionally filters by asset_class.

    Returns list of lightweight dicts: ticker, name, asset_class, PX_LAST, CRNCY.
    """
    query_lower = query.lower()
    results = []

    for key, sec in SECURITIES.items():
        if asset_class and sec.get("asset_class") != asset_class:
            continue

        searchable = " ".join(
            str(v)
            for v in [
                sec.get("ticker", ""),
                sec.get("short_ticker", ""),
                sec.get("name", ""),
            ]
        ).lower()

        if query_lower in searchable:
            results.append(
                {
                    "ticker": sec["ticker"],
                    "name": sec["name"],
                    "asset_class": sec["asset_class"],
                    "PX_LAST": sec.get("PX_LAST"),
                    "CRNCY": sec.get("CRNCY", "USD"),
                }
            )

    # Sort by ticker for stable ordering
    results.sort(key=lambda r: r["ticker"])
    return results
