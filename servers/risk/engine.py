"""Mock risk engine.

Provides realistic simulated VaR, Greeks, and scenario calculations
for a multi-desk derivatives/options fund.
"""

from __future__ import annotations

import math
import random
from typing import Any

# ---------------------------------------------------------------------------
# Desk portfolio metadata
# ---------------------------------------------------------------------------

DESK_PORTFOLIOS: dict[str, dict[str, Any]] = {
    "vol": {
        "aum_usd": 1_200_000_000,   # $1.2B — largest, pure vol-arb
        "position_count": 847,
        "option_notional_usd": 4_800_000_000,  # high leverage from options
        "underlying_universe": ["SPX", "NDX", "RUT", "VIX", "AAPL", "NVDA", "TSLA", "META", "AMZN", "GOOGL"],
        "primary_expiry_days": 30,
        "avg_strike_moneyness": 0.98,
        "net_delta": -0.12,          # slightly short delta (delta-hedged)
        "net_vega": 2_450_000,       # long vol — primary risk driver
        "net_gamma": 185_000,
        "net_theta": -380_000,       # theta bleed from long options
        "net_rho": -95_000,
        "vol_regime": "elevated",
    },
    "equities": {
        "aum_usd": 950_000_000,      # $950M — long/short equity
        "position_count": 412,
        "option_notional_usd": 1_200_000_000,
        "underlying_universe": ["SPX", "QQQ", "AAPL", "MSFT", "GOOGL", "META", "NVDA", "JPM", "GS", "BAC"],
        "primary_expiry_days": 45,
        "avg_strike_moneyness": 1.02,
        "net_delta": 0.38,           # net long bias
        "net_vega": 890_000,
        "net_gamma": 42_000,
        "net_theta": -125_000,
        "net_rho": 210_000,
        "vol_regime": "normal",
    },
    "rates": {
        "aum_usd": 1_500_000_000,    # $1.5B — fixed income + swaptions
        "position_count": 289,
        "option_notional_usd": 6_200_000_000,  # large notional from swaptions
        "underlying_universe": ["UST2Y", "UST5Y", "UST10Y", "UST30Y", "SOFR", "EUR5Y", "EUR10Y"],
        "primary_expiry_days": 90,
        "avg_strike_moneyness": 1.0,
        "net_delta": -0.05,          # duration-neutral (DV01 managed separately)
        "net_vega": 1_850_000,
        "net_gamma": 68_000,
        "net_theta": -210_000,
        "net_rho": -1_420_000,       # significant rate sensitivity
        "vol_regime": "normal",
    },
    "macro": {
        "aum_usd": 750_000_000,      # $750M — global macro
        "position_count": 156,
        "option_notional_usd": 2_800_000_000,
        "underlying_universe": ["SPX", "EURUSD", "USDJPY", "GBPUSD", "GLD", "CL", "UST10Y"],
        "primary_expiry_days": 60,
        "avg_strike_moneyness": 0.97,
        "net_delta": 0.22,
        "net_vega": 620_000,
        "net_gamma": 28_000,
        "net_theta": -88_000,
        "net_rho": -340_000,
        "vol_regime": "normal",
    },
    "credit": {
        "aum_usd": 500_000_000,      # $500M — credit derivatives
        "position_count": 203,
        "option_notional_usd": 1_500_000_000,
        "underlying_universe": ["CDX.IG", "CDX.HY", "ITRAXX", "IG_OPTIONS", "HY_OPTIONS"],
        "primary_expiry_days": 120,
        "avg_strike_moneyness": 1.0,
        "net_delta": 0.08,
        "net_vega": 380_000,
        "net_gamma": 15_000,
        "net_theta": -52_000,
        "net_rho": 185_000,
        "vol_regime": "stressed",
    },
}

# Scenario shock magnitudes (base, before magnitude multiplier)
SCENARIO_BASE_SHOCKS: dict[str, dict[str, float]] = {
    "vol_spike": {
        "vol_shift_pct": 0.30,       # 30% vol increase
        "equity_move_pct": -0.05,    # -5% equity accompanying move
        "rate_shift_bps": 10,
        "spread_widening_bps": 25,
    },
    "rate_shock": {
        "vol_shift_pct": 0.10,
        "equity_move_pct": -0.03,
        "rate_shift_bps": 100,       # +100bps parallel shift
        "spread_widening_bps": 15,
    },
    "equity_crash": {
        "vol_shift_pct": 0.80,       # vol doubles+ in crash
        "equity_move_pct": -0.15,    # -15% equity drop
        "rate_shift_bps": -25,       # flight to quality
        "spread_widening_bps": 150,
    },
    "custom": {
        "vol_shift_pct": 0.20,
        "equity_move_pct": -0.08,
        "rate_shift_bps": 50,
        "spread_widening_bps": 40,
    },
}


# ---------------------------------------------------------------------------
# VaR / CVaR engine
# ---------------------------------------------------------------------------

def calculate_var(
    desk: str,
    metric: str,
    confidence: float,
    horizon_days: int,
) -> dict[str, Any]:
    """
    Simulate historical-simulation VaR/CVaR for a desk.

    Returns realistic dollar and percentage values scaled to desk AUM.
    """
    portfolio = DESK_PORTFOLIOS[desk]
    nav = portfolio["aum_usd"]
    vol_regime = portfolio["vol_regime"]

    # Base daily vol assumptions per regime (annualized, converted to daily)
    daily_vol_map = {
        "normal": 0.012,    # 1.2% daily
        "elevated": 0.018,  # 1.8% daily
        "stressed": 0.022,  # 2.2% daily
    }
    base_daily_vol = daily_vol_map.get(vol_regime, 0.015)

    # Scale vol by options leverage — option books amplify tail risk
    leverage_factor = portfolio["option_notional_usd"] / portfolio["aum_usd"]
    effective_vol = base_daily_vol * math.sqrt(min(leverage_factor * 0.15 + 0.85, 2.5))

    # Horizon scaling (square-root-of-time)
    horizon_vol = effective_vol * math.sqrt(horizon_days)

    # Confidence-level z-scores for historical simulation (fat-tailed)
    # Using Cornish-Fisher expansion approximation
    z_map = {
        0.90: 1.28,
        0.95: 1.645,
        0.99: 2.326,
        0.999: 3.090,
        0.9999: 3.719,
    }
    # Interpolate z-score
    z = _interpolate_z(confidence, z_map)

    # Add small random jitter for realism (±3%)
    rng = random.Random(hash((desk, metric, confidence, horizon_days)) % (2**31))
    jitter = 1.0 + rng.uniform(-0.03, 0.03)

    if metric == "var":
        value_pct_nav = horizon_vol * z * jitter
        value_usd = value_pct_nav * nav

        return {
            "desk": desk,
            "metric": "var",
            "value_usd": round(value_usd, 0),
            "value_pct_nav": round(value_pct_nav * 100, 4),
            "nav": nav,
            "method": "historical_simulation",
            "lookback_days": 504,   # 2 years
            "confidence_interval": confidence,
            "horizon_days": horizon_days,
            "daily_vol_regime": vol_regime,
            "effective_daily_vol_pct": round(effective_vol * 100, 3),
        }

    elif metric == "cvar":
        # CVaR / Expected Shortfall — approximately 1.25x VaR for fat tails
        # More precisely: E[loss | loss > VaR] — use higher z factor
        cvar_multiplier = _cvar_multiplier(confidence)
        value_pct_nav = horizon_vol * z * cvar_multiplier * jitter
        value_usd = value_pct_nav * nav

        return {
            "desk": desk,
            "metric": "cvar",
            "value_usd": round(value_usd, 0),
            "value_pct_nav": round(value_pct_nav * 100, 4),
            "nav": nav,
            "method": "historical_simulation",
            "lookback_days": 504,
            "confidence_interval": confidence,
            "horizon_days": horizon_days,
            "daily_vol_regime": vol_regime,
            "effective_daily_vol_pct": round(effective_vol * 100, 3),
            "cvar_multiplier": round(cvar_multiplier, 3),
        }

    else:
        # For other metrics (delta/gamma/vega/theta/rho), return a simple scalar
        greek_val = _get_greek_scalar(portfolio, metric)
        return {
            "desk": desk,
            "metric": metric,
            "value": greek_val,
            "nav": nav,
            "method": "mark_to_market",
            "horizon_days": horizon_days,
        }


def _interpolate_z(confidence: float, z_map: dict[float, float]) -> float:
    """Linear interpolation for z-score given confidence level."""
    keys = sorted(z_map)
    if confidence <= keys[0]:
        return z_map[keys[0]]
    if confidence >= keys[-1]:
        return z_map[keys[-1]]
    for i in range(len(keys) - 1):
        lo, hi = keys[i], keys[i + 1]
        if lo <= confidence <= hi:
            t = (confidence - lo) / (hi - lo)
            return z_map[lo] + t * (z_map[hi] - z_map[lo])
    return 2.326  # fallback 99%


def _cvar_multiplier(confidence: float) -> float:
    """Return CVaR/VaR ratio for given confidence (fat-tailed distribution)."""
    if confidence >= 0.999:
        return 1.45
    elif confidence >= 0.99:
        return 1.32
    elif confidence >= 0.95:
        return 1.22
    return 1.15


def _get_greek_scalar(portfolio: dict, metric: str) -> float:
    """Return the portfolio-level Greek value."""
    key_map = {
        "delta": "net_delta",
        "gamma": "net_gamma",
        "vega": "net_vega",
        "theta": "net_theta",
        "rho": "net_rho",
    }
    key = key_map.get(metric, "net_delta")
    return portfolio.get(key, 0.0)


# ---------------------------------------------------------------------------
# Greeks aggregation engine
# ---------------------------------------------------------------------------

def aggregate_greeks(desk: str, underlying: str | None = None) -> dict[str, Any]:
    """
    Return aggregate portfolio Greeks with per-underlying breakdown.

    For options-heavy desks, values reflect realistic options book sensitivities.
    """
    portfolio = DESK_PORTFOLIOS[desk]
    nav = portfolio["aum_usd"]
    universe = portfolio["underlying_universe"]

    # If filtering by underlying, check it exists in this desk's universe
    if underlying:
        underlying = underlying.upper()
        if underlying not in universe:
            return {
                "desk": desk,
                "underlying_filter": underlying,
                "error": f"Underlying '{underlying}' not found in {desk} desk universe",
                "available_underlyings": universe,
            }

    # Aggregate Greeks (portfolio-level)
    aggregate = {
        "delta": portfolio["net_delta"],
        "gamma": portfolio["net_gamma"],
        "vega": portfolio["net_vega"],
        "theta": portfolio["net_theta"],
        "rho": portfolio["net_rho"],
    }

    # Top contributors (simulate per-underlying breakdown)
    contributors = _generate_contributors(portfolio, underlying)

    result: dict[str, Any] = {
        "desk": desk,
        "nav": nav,
        "position_count": portfolio["position_count"],
        "aggregate_greeks": aggregate,
        "top_contributors": contributors,
        "units": {
            "delta": "notional_equivalent_usd_per_1pct_move",
            "gamma": "usd_per_1pct_move_squared",
            "vega": "usd_per_1vol_point",
            "theta": "usd_per_day",
            "rho": "usd_per_1bp_rate_move",
        },
    }

    if underlying:
        result["underlying_filter"] = underlying

    return result


def _generate_contributors(
    portfolio: dict, underlying: str | None
) -> list[dict[str, Any]]:
    """Generate realistic top-contributor breakdown per underlying."""
    universe = portfolio["underlying_universe"]
    if underlying:
        names = [underlying]
    else:
        names = universe[:5]  # top 5

    net_vega = portfolio["net_vega"]
    net_gamma = portfolio["net_gamma"]
    net_delta = portfolio["net_delta"]

    # Distribute Greeks across underlyings with realistic concentration
    weights = [0.30, 0.20, 0.18, 0.17, 0.15]
    if underlying:
        weights = [1.0]

    contributors = []
    for i, name in enumerate(names):
        w = weights[i] if i < len(weights) else 0.05
        rng = random.Random(hash(name) % (2**31))
        sign_delta = 1 if rng.random() > 0.4 else -1

        contributors.append({
            "underlying": name,
            "delta": round(net_delta * w * (1 + rng.uniform(-0.2, 0.2)) * sign_delta, 4),
            "gamma": round(net_gamma * w * (1 + rng.uniform(-0.15, 0.15)), 0),
            "vega": round(net_vega * w * (1 + rng.uniform(-0.10, 0.10)), 0),
            "theta": round(portfolio["net_theta"] * w * (1 + rng.uniform(-0.2, 0.2)), 0),
            "open_interest": rng.randint(50, 800),
            "net_position_usd": round(
                portfolio["aum_usd"] * w * rng.uniform(0.05, 0.25) * sign_delta, 0
            ),
        })

    return contributors


# ---------------------------------------------------------------------------
# Scenario engine
# ---------------------------------------------------------------------------

def run_scenario(
    desk: str,
    scenario: str,
    magnitude: float,
) -> dict[str, Any]:
    """
    Compute stress test PnL impact for a given scenario and magnitude multiplier.

    Returns pnl_impact, worst_position, recovery_estimate, and greeks_shift.
    """
    portfolio = DESK_PORTFOLIOS[desk]
    nav = portfolio["aum_usd"]
    shocks = SCENARIO_BASE_SHOCKS.get(scenario, SCENARIO_BASE_SHOCKS["custom"])

    vol_shock = shocks["vol_shift_pct"] * magnitude
    equity_shock = shocks["equity_move_pct"] * magnitude
    rate_shock_bps = shocks["rate_shift_bps"] * magnitude
    spread_shock_bps = shocks["spread_widening_bps"] * magnitude

    # PnL decomposition
    delta_pnl = portfolio["net_delta"] * nav * equity_shock
    vega_pnl = portfolio["net_vega"] * vol_shock * 100  # vega per vol point
    gamma_pnl = 0.5 * portfolio["net_gamma"] * (equity_shock ** 2) * (nav ** 2 / 1e12)
    theta_pnl = 0.0  # scenario is instantaneous
    rho_pnl = portfolio["net_rho"] * rate_shock_bps

    # Credit spread impact (spread_dv01 approximation)
    spread_dv01 = nav * 0.000015  # ~$15k per bp per $1B
    spread_pnl = -spread_dv01 * spread_shock_bps

    total_pnl = delta_pnl + vega_pnl + gamma_pnl + rho_pnl + spread_pnl

    # Worst position — pick from universe with realistic loss
    universe = portfolio["underlying_universe"]
    rng = random.Random(hash((desk, scenario)) % (2**31))
    worst_underlying = universe[rng.randint(0, min(2, len(universe) - 1))]
    worst_pnl = total_pnl * rng.uniform(0.25, 0.45)  # worst position = 25-45% of total

    # Recovery estimate (business days to recover through theta/carry)
    daily_carry = abs(portfolio["net_theta"]) * 1.5  # theta + other carry
    if daily_carry > 0 and total_pnl < 0:
        recovery_days = int(abs(total_pnl) / daily_carry)
        recovery_estimate = f"{recovery_days} trading days"
    elif total_pnl >= 0:
        recovery_estimate = "N/A (net gain scenario)"
    else:
        recovery_estimate = "Unknown — structural position change needed"

    # Greeks shift post-scenario
    vol_delta_shift = vol_shock * 0.01  # higher vol increases delta sensitivity
    greeks_shift = {
        "delta_change": round(portfolio["net_delta"] * vol_delta_shift * (1 if equity_shock < 0 else -1), 4),
        "gamma_change": round(portfolio["net_gamma"] * vol_shock * 0.5, 0),
        "vega_change": round(portfolio["net_vega"] * (-0.05 if scenario == "vol_spike" else 0.02) * magnitude, 0),
        "theta_change": round(portfolio["net_theta"] * vol_shock * 0.3, 0),
    }

    return {
        "desk": desk,
        "scenario": scenario,
        "magnitude": magnitude,
        "nav": nav,
        "pnl_impact": {
            "total_usd": round(total_pnl, 0),
            "total_pct_nav": round((total_pnl / nav) * 100, 4),
            "decomposition": {
                "delta_pnl_usd": round(delta_pnl, 0),
                "vega_pnl_usd": round(vega_pnl, 0),
                "gamma_pnl_usd": round(gamma_pnl, 0),
                "rho_pnl_usd": round(rho_pnl, 0),
                "spread_pnl_usd": round(spread_pnl, 0),
            },
        },
        "worst_position": {
            "underlying": worst_underlying,
            "estimated_pnl_usd": round(worst_pnl, 0),
            "pct_of_total_loss": round(abs(worst_pnl / total_pnl) * 100, 1) if total_pnl != 0 else 0.0,
        },
        "recovery_estimate": recovery_estimate,
        "greeks_shift": greeks_shift,
        "scenario_shocks_applied": {
            "vol_shift_pct": round(vol_shock * 100, 1),
            "equity_move_pct": round(equity_shock * 100, 1),
            "rate_shift_bps": round(rate_shock_bps, 1),
            "spread_widening_bps": round(spread_shock_bps, 1),
        },
    }
