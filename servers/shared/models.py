"""Shared Pydantic models used across MCP servers."""

from __future__ import annotations

from typing import Literal, Optional
from datetime import date

from pydantic import BaseModel, Field

DeskId = Literal["equities", "rates", "vol", "macro", "credit"]


class PositionsQuery(BaseModel):
    desk: DeskId = Field(description="Trading desk identifier")
    as_of_date: Optional[date] = Field(
        default=None, description="Snapshot date (ISO 8601). Defaults to today."
    )
    min_notional: Optional[float] = Field(
        default=None, description="Filter: positions with |notional| > threshold", ge=0
    )
    asset_class: Optional[Literal["equity", "option", "future", "bond", "fx"]] = None


class RiskQuery(BaseModel):
    desk: DeskId
    metric: Literal["var", "cvar", "delta", "gamma", "vega", "theta", "rho"] = Field(
        description="Risk metric to calculate"
    )
    confidence: float = Field(default=0.99, ge=0.90, le=0.9999)
    horizon_days: int = Field(default=1, ge=1, le=252)


class ScenarioParams(BaseModel):
    desk: DeskId
    scenario: Literal["vol_spike", "rate_shock", "equity_crash", "custom"] = Field(
        description="Pre-defined stress scenario"
    )
    magnitude: float = Field(
        default=2.0, ge=0.1, le=10.0, description="Scenario severity multiplier"
    )


class GreeksQuery(BaseModel):
    desk: DeskId
    underlying: Optional[str] = Field(
        default=None, description="Filter to options on a specific underlying"
    )
