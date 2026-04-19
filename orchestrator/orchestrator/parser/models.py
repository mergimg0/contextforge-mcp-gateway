"""
Pydantic models for the thesis parser layer.

A ThesisStatement is the structured representation of a natural-language
investment thesis.  The parser extracts all fields from raw text using
keyword matching and pattern rules — no LLM dependency.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ClaimType(str, Enum):
    """The core analytical claim being made in the thesis."""

    VOL_MISPRICING = "vol_mispricing"
    MOMENTUM = "momentum"
    RELATIVE_VALUE = "relative_value"
    EVENT_DRIVEN = "event_driven"
    MACRO = "macro"
    MEAN_REVERSION = "mean_reversion"


class Direction(str, Enum):
    """Directional bias of the thesis trade."""

    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"
    LONG_VOL = "long_vol"
    SHORT_VOL = "short_vol"


class AssetClass(str, Enum):
    """Broad asset class of the primary instrument."""

    EQUITY = "equity"
    OPTIONS = "options"
    FIXED_INCOME = "fixed_income"
    FX = "fx"
    COMMODITY = "commodity"
    INDEX = "index"
    CREDIT = "credit"
    MULTI_ASSET = "multi_asset"


class ThesisStatement(BaseModel):
    """
    Structured representation of an investment thesis, parsed from natural language.

    Fields mirror the analytical dimensions a PM would articulate when presenting
    a trade idea to a risk committee.
    """

    raw_text: str = Field(description="Original thesis text as submitted by the PM")

    # Core identification
    asset: str = Field(description="Primary instrument or ticker (e.g. 'AAPL', 'SPX')")
    asset_class: AssetClass = Field(description="Broad asset class")
    claim_type: ClaimType = Field(description="The core analytical claim")

    # Directional / magnitude
    direction: Direction = Field(description="Directional bias of the trade")
    magnitude: Optional[str] = Field(
        default=None,
        description="Quantitative magnitude if stated (e.g. '95th percentile', '+50bps', '2 sigma')",
    )

    # Time horizon
    timeframe: Optional[str] = Field(
        default=None,
        description="Investment horizon if stated (e.g. '30-day', 'Q2 2025', '6 months')",
    )

    # Trade structure
    proposed_trade: Optional[str] = Field(
        default=None,
        description="Specific trade structure if inferable (e.g. 'buy straddle', 'long spread')",
    )

    # Validation readiness
    testable: bool = Field(
        default=True,
        description="Whether the thesis can be validated with available data tools",
    )
    untestable_reason: Optional[str] = Field(
        default=None,
        description="If not testable, explains why",
    )

    # What data is needed
    data_requirements: list[str] = Field(
        default_factory=list,
        description="List of data types required to validate this thesis",
    )

    # Confidence in the parse
    parse_confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Parser confidence in the extraction (0–1)",
    )
