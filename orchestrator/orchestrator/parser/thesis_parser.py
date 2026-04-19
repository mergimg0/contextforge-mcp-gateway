"""
Thesis Parser — converts natural-language investment theses into structured
ThesisStatement objects using keyword matching and pattern rules.

No LLM dependency: all extraction is deterministic so the pipeline is
predictable, fast, and testable.

Realistic thesis examples handled:
  - "AAPL implied vol is mispriced relative to realised. 30-day IV-RV spread
    at 95th percentile."
  - "Tech sector showing momentum divergence from SPX. RSI overbought."
  - "Investment grade credit spreads are too tight. Mean reversion expected."
  - "NVDA earnings catalyst, expect 10% gap risk. Long straddle."
  - "USD/JPY rate differential too wide vs fundamentals. Short USD."
"""

from __future__ import annotations

import re
from typing import Optional

import structlog

from .models import AssetClass, ClaimType, Direction, ThesisStatement

log = structlog.get_logger("orchestrator.parser")

# ---------------------------------------------------------------------------
# Keyword tables
# ---------------------------------------------------------------------------

_CLAIM_KEYWORDS: dict[ClaimType, list[str]] = {
    ClaimType.VOL_MISPRICING: [
        "implied vol",
        "implied volatility",
        "iv-rv",
        "iv/rv",
        "vol mispriced",
        "volatility mispriced",
        "vol premium",
        "volatility premium",
        "options mispriced",
        "skew mispriced",
        "vol surface",
        "vix",
        "realized vol",
        "realised vol",
        "iv spread",
        "vol spread",
    ],
    ClaimType.MOMENTUM: [
        "momentum",
        "rsi",
        "relative strength",
        "overbought",
        "oversold",
        "breakout",
        "trend following",
        "trend continuation",
        "price momentum",
        "divergence",
        "moving average crossover",
        "macd",
        "technical breakout",
    ],
    ClaimType.RELATIVE_VALUE: [
        "relative value",
        "spread too tight",
        "spread too wide",
        "basis trade",
        "pair trade",
        "pairs trade",
        "spread trade",
        "relative cheapness",
        "relative richness",
        "z-score",
        "percentile spread",
        "fair value",
        "mispriced relative to",
        "rich vs",
        "cheap vs",
        "outperform",
        "underperform",
    ],
    ClaimType.EVENT_DRIVEN: [
        "earnings",
        "catalyst",
        "earnings catalyst",
        "gap risk",
        "event risk",
        "merger",
        "acquisition",
        "m&a",
        "spin-off",
        "spinoff",
        "ipo",
        "secondary offering",
        "guidance",
        "regulatory",
        "fda",
        "announcement",
        "conference",
    ],
    ClaimType.MACRO: [
        "macro",
        "rate differential",
        "yield curve",
        "central bank",
        "fed",
        "fomc",
        "boe",
        "ecb",
        "boj",
        "inflation",
        "gdp",
        "employment",
        "pmis",
        "purchasing managers",
        "current account",
        "trade deficit",
        "geopolitical",
        "currency",
        "fx",
        "usd",
        "eur",
        "jpy",
    ],
    ClaimType.MEAN_REVERSION: [
        "mean reversion",
        "mean-reversion",
        "revert to mean",
        "revert to the mean",
        "too tight",
        "too wide",
        "historically elevated",
        "historically depressed",
        "extreme",
        "abnormal",
        "stretched",
        "overextended",
        "correction expected",
        "snap back",
        "snapback",
        "normalise",
        "normalize",
    ],
}

_DIRECTION_KEYWORDS: dict[Direction, list[str]] = {
    Direction.LONG_VOL: [
        "long vol",
        "long volatility",
        "buy vol",
        "buy volatility",
        "long straddle",
        "long strangle",
        "buy straddle",
        "buy strangle",
        "long calls",
        "long puts",
        "vega long",
        "buy options",
        "long gamma",
    ],
    Direction.SHORT_VOL: [
        "short vol",
        "short volatility",
        "sell vol",
        "sell volatility",
        "short straddle",
        "short strangle",
        "sell straddle",
        "sell strangle",
        "short calls",
        "short puts",
        "vega short",
        "sell options",
        "short gamma",
        "write options",
    ],
    Direction.SHORT: [
        "short",
        "sell",
        "bearish",
        "bear",
        "put spread",
        "downside",
        "decline",
        "fall",
        "drop",
        "overvalued",
        "rich",
        "overbought",
    ],
    Direction.LONG: [
        "long",
        "buy",
        "bullish",
        "bull",
        "call spread",
        "upside",
        "rise",
        "rally",
        "undervalued",
        "cheap",
        "oversold",
    ],
}

_ASSET_CLASS_PATTERNS: list[tuple[re.Pattern, AssetClass]] = [
    (re.compile(r"\b(credit spread|IG|HY|high yield|investment grade|cds|credit default)\b", re.I), AssetClass.CREDIT),
    (re.compile(r"\b(option|straddle|strangle|put|call|vol surface|implied vol)\b", re.I), AssetClass.OPTIONS),
    (re.compile(r"\b(treasury|yield|rate|bond|note|duration|spread|bps|basis points)\b", re.I), AssetClass.FIXED_INCOME),
    (re.compile(r"\b(USD|EUR|JPY|GBP|CHF|AUD|NZD|FX|forex|currency)\b", re.I), AssetClass.FX),
    (re.compile(r"\b(SPX|NDX|Russell|FTSE|DAX|Nikkei|index|sector ETF)\b", re.I), AssetClass.INDEX),
    (re.compile(r"\b(crude|oil|gas|gold|silver|copper|commodity|commodity)\b", re.I), AssetClass.COMMODITY),
    (re.compile(r"\b(equity|stock|shares|equities)\b", re.I), AssetClass.EQUITY),
]

# Common known tickers — used for asset extraction
_KNOWN_TICKERS = {
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM", "GS",
    "MS", "BAC", "C", "WFC", "SPX", "NDX", "VIX", "SPY", "QQQ", "IWM",
    "TLT", "HYG", "LQD", "GLD", "USO", "XLK", "XLF", "XLE", "XLV",
    "USD", "EUR", "JPY", "GBP",
}

_DATA_REQUIREMENTS: dict[ClaimType, list[str]] = {
    ClaimType.VOL_MISPRICING: [
        "implied volatility history (30d)",
        "realized volatility history (30d)",
        "IV-RV spread percentile",
        "option greeks (vega, gamma)",
        "event calendar",
        "vol scenario P&L",
    ],
    ClaimType.MOMENTUM: [
        "price history (90d)",
        "RSI / technical indicators",
        "sector comparison",
        "VaR at confidence level",
        "sector research",
    ],
    ClaimType.RELATIVE_VALUE: [
        "spread history",
        "current spread vs historical range",
        "pair correlation",
        "scenario analysis",
        "fundamental research",
    ],
    ClaimType.EVENT_DRIVEN: [
        "event calendar",
        "implied move (straddle pricing)",
        "historical event drift",
        "option greeks pre-event",
        "event scenario P&L",
        "analyst estimates",
    ],
    ClaimType.MACRO: [
        "macro factor history",
        "yield curve data",
        "FX rate history",
        "cross-asset correlations",
        "macro research",
        "rate shock scenario",
    ],
    ClaimType.MEAN_REVERSION: [
        "spread vs historical mean",
        "z-score / percentile rank",
        "mean-reversion velocity",
        "scenario analysis",
        "fundamental anchor research",
    ],
}


# ---------------------------------------------------------------------------
# Magnitude extraction
# ---------------------------------------------------------------------------

_MAGNITUDE_PATTERNS = [
    re.compile(r"(\d+(?:\.\d+)?)\s*(?:th|st|nd|rd)?\s*percentile", re.I),
    re.compile(r"(\d+(?:\.\d+)?)\s*%\s*(?:gap|move|target|upside|downside)", re.I),
    re.compile(r"(\d+(?:\.\d+)?)\s*(?:bps|bp)\b", re.I),
    re.compile(r"(\d+(?:\.\d+)?)\s*(?:sigma|std)", re.I),
    re.compile(r"(\d+(?:\.\d+)?)\s*x\s*(?:historical|normal|average)", re.I),
    re.compile(r"z-?score\s+(?:of\s+)?([+-]?\d+(?:\.\d+)?)", re.I),
]

# ---------------------------------------------------------------------------
# Timeframe extraction
# ---------------------------------------------------------------------------

_TIMEFRAME_PATTERNS = [
    re.compile(r"(\d+)\s*-?\s*(day|week|month|year)s?\b", re.I),
    re.compile(r"(Q[1-4]\s*\d{4}|\d{4}\s*Q[1-4])", re.I),
    re.compile(r"(near.?term|short.?term|medium.?term|long.?term)", re.I),
    re.compile(r"(into|ahead of|before|after)\s+(earnings|the\s+\w+\s+meeting|expiry|expiration)", re.I),
    re.compile(r"(30|60|90|180|252)\s*-?\s*day", re.I),
]

# ---------------------------------------------------------------------------
# Trade structure extraction
# ---------------------------------------------------------------------------

_TRADE_PATTERNS = [
    re.compile(r"\b(long|short)\s+(straddle|strangle|call|put|spread|fly|butterfly)\b", re.I),
    re.compile(r"\b(buy|sell)\s+(straddle|strangle|call|put|spread|protection)\b", re.I),
    re.compile(r"\b(risk reversal|ratio spread|calendar spread|diagonal)\b", re.I),
    re.compile(r"\b(long|short)\s+(the\s+)?(stock|equity|position|basis|spread)\b", re.I),
    re.compile(r"\b(pairs trade|relative value trade|stat arb)\b", re.I),
    re.compile(r"\b(buy|sell)\s+(protection|the\s+dip|the\s+rally)\b", re.I),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_thesis(raw_text: str) -> ThesisStatement:
    """
    Parse a natural-language investment thesis into a structured ThesisStatement.

    Uses keyword matching and regex patterns.  Returns a ThesisStatement with
    parse_confidence indicating extraction quality.

    Args:
        raw_text: Free-form thesis text from a PM or analyst.

    Returns:
        ThesisStatement with all extracted fields populated.
    """
    text_lower = raw_text.lower()

    claim_type = _extract_claim_type(text_lower)
    asset, asset_class = _extract_asset_and_class(raw_text, text_lower, claim_type)
    direction = _extract_direction(text_lower, claim_type)
    magnitude = _extract_magnitude(raw_text)
    timeframe = _extract_timeframe(raw_text, text_lower)
    proposed_trade = _extract_proposed_trade(raw_text)
    data_reqs = _DATA_REQUIREMENTS.get(claim_type, [])

    # Assess testability — thesis is untestable only if we cannot identify an asset
    testable = asset != "UNKNOWN"
    untestable_reason = None if testable else (
        "Could not identify a specific asset or instrument from the thesis text. "
        "Please specify a ticker, index, or instrument name."
    )

    # Parse confidence: penalise if asset or claim_type defaulted
    confidence = 1.0
    if asset == "UNKNOWN":
        confidence -= 0.3
    if claim_type == ClaimType.RELATIVE_VALUE and "relative" not in text_lower:
        confidence -= 0.1
    if direction == Direction.NEUTRAL:
        confidence -= 0.1
    confidence = max(0.0, round(confidence, 2))

    log.info(
        "thesis_parsed",
        asset=asset,
        claim_type=claim_type.value,
        direction=direction.value,
        testable=testable,
        confidence=confidence,
    )

    return ThesisStatement(
        raw_text=raw_text,
        asset=asset,
        asset_class=asset_class,
        claim_type=claim_type,
        direction=direction,
        magnitude=magnitude,
        timeframe=timeframe,
        proposed_trade=proposed_trade,
        testable=testable,
        untestable_reason=untestable_reason,
        data_requirements=data_reqs,
        parse_confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_claim_type(text_lower: str) -> ClaimType:
    """Score each claim type by keyword hit count; return the winner."""
    scores: dict[ClaimType, int] = {ct: 0 for ct in ClaimType}
    for claim_type, keywords in _CLAIM_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                scores[claim_type] += 1

    best = max(scores, key=lambda ct: scores[ct])
    # If no signal at all, fall back to relative_value (most generic)
    if scores[best] == 0:
        return ClaimType.RELATIVE_VALUE
    return best


def _extract_asset_and_class(raw_text: str, text_lower: str, claim_type: ClaimType) -> tuple[str, AssetClass]:
    """
    Extract primary asset ticker/name and its asset class.

    Strategy:
    1. Look for known tickers (uppercase words matching _KNOWN_TICKERS)
    2. Look for 1-5 letter uppercase sequences as potential tickers
    3. Try regex patterns for asset class
    4. Fall back on claim_type hints
    """
    # 1. Known tickers — search raw text (case-sensitive)
    words = re.findall(r"\b([A-Z]{1,5}(?:/[A-Z]{2,4})?)\b", raw_text)
    for word in words:
        if word in _KNOWN_TICKERS:
            asset_class = _classify_asset(word, text_lower, claim_type)
            return word, asset_class

    # 2. Fallback — try to find any 2-5 letter uppercase word that looks like a ticker
    candidates = [w for w in words if 2 <= len(w) <= 5 and w not in {"IV", "OR", "BY", "IF", "AT", "VS", "TO", "IN", "ON", "OF", "IS", "IT", "AN", "PM", "RSI", "RV", "IG", "HY"}]
    if candidates:
        asset = candidates[0]
        asset_class = _classify_asset(asset, text_lower, claim_type)
        return asset, asset_class

    # 3. Try to extract asset from common phrases
    named_match = re.search(
        r"\b(tech sector|credit spreads?|investment grade|high yield|yield curve|US treasur|equity market)\b",
        text_lower,
    )
    if named_match:
        phrase = named_match.group(1).upper().replace(" ", "_")
        asset_class = _classify_asset_from_class_hint(text_lower, claim_type)
        return phrase, asset_class

    # 4. No ticker found
    asset_class = _classify_asset_from_class_hint(text_lower, claim_type)
    return "UNKNOWN", asset_class


def _classify_asset(ticker: str, text_lower: str, claim_type: ClaimType) -> AssetClass:
    """Classify asset class from ticker and surrounding context."""
    # FX pairs
    if "/" in ticker or ticker in {"USD", "EUR", "JPY", "GBP", "CHF", "AUD"}:
        return AssetClass.FX

    # Known indices
    if ticker in {"SPX", "NDX", "VIX", "SPY", "QQQ", "IWM", "XLK", "XLF", "XLE", "XLV"}:
        return AssetClass.INDEX

    # Fixed income ETFs
    if ticker in {"TLT", "HYG", "LQD", "AGG"}:
        return AssetClass.FIXED_INCOME if ticker == "TLT" else AssetClass.CREDIT

    # Commodities
    if ticker in {"GLD", "USO", "GC", "CL"}:
        return AssetClass.COMMODITY

    # Claim-type hints
    return _classify_asset_from_class_hint(text_lower, claim_type)


def _classify_asset_from_class_hint(text_lower: str, claim_type: ClaimType) -> AssetClass:
    """Classify asset class from text patterns and claim type."""
    # Try regex patterns
    for pattern, asset_class in _ASSET_CLASS_PATTERNS:
        if pattern.search(text_lower):
            return asset_class

    # Claim-type fallback
    claim_defaults = {
        ClaimType.VOL_MISPRICING: AssetClass.OPTIONS,
        ClaimType.MACRO: AssetClass.MULTI_ASSET,
        ClaimType.MEAN_REVERSION: AssetClass.CREDIT,
    }
    return claim_defaults.get(claim_type, AssetClass.EQUITY)


def _extract_direction(text_lower: str, claim_type: ClaimType) -> Direction:
    """Score each direction by keyword hit count."""
    scores: dict[Direction, int] = {d: 0 for d in Direction}
    for direction, keywords in _DIRECTION_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                scores[direction] += 1

    # Vol mispricing defaults to long_vol when direction is unclear
    if max(scores.values()) == 0:
        if claim_type == ClaimType.VOL_MISPRICING:
            return Direction.LONG_VOL
        if claim_type == ClaimType.MEAN_REVERSION:
            return Direction.NEUTRAL
        return Direction.NEUTRAL

    best = max(scores, key=lambda d: scores[d])
    return best


def _extract_magnitude(raw_text: str) -> Optional[str]:
    """Extract a quantitative magnitude expression from the thesis text."""
    for pattern in _MAGNITUDE_PATTERNS:
        match = pattern.search(raw_text)
        if match:
            return match.group(0).strip()
    return None


def _extract_timeframe(raw_text: str, text_lower: str) -> Optional[str]:
    """Extract a time horizon expression from the thesis text."""
    for pattern in _TIMEFRAME_PATTERNS:
        match = pattern.search(raw_text)
        if match:
            return match.group(0).strip()
    return None


def _extract_proposed_trade(raw_text: str) -> Optional[str]:
    """Extract a proposed trade structure from the thesis text."""
    for pattern in _TRADE_PATTERNS:
        match = pattern.search(raw_text)
        if match:
            return match.group(0).strip()
    return None
