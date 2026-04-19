"""
Mock research document store for the Research MCP server.

Contains 20 sample research documents relevant to a derivatives/options
hedge fund, with topics spanning vol surface analysis, IV-RV spreads,
earnings volatility, sector dispersion, macro vol regimes, Greek
sensitivities, options flow, and correlation studies.
"""

from __future__ import annotations

import math
import re
from typing import Optional


# ---------------------------------------------------------------------------
# Document data
# ---------------------------------------------------------------------------

DOCUMENTS: list[dict] = [
    # ------------------------------------------------------------------ #
    # 1. Vol surface analysis
    # ------------------------------------------------------------------ #
    {
        "id": "VOL-2025-001",
        "title": "SPX Volatility Surface Dynamics: Skew Richness and Term Structure Flattening",
        "author": "Elena Marchetti",
        "date": "2025-02-14",
        "tags": ["vol surface", "skew", "SPX", "term structure"],
        "desk_relevance": ["vol", "equities"],
        "content": (
            "The SPX 25-delta risk-reversal has cheapened by ~1.5 vol points since early "
            "January, settling near -6.2 for the 3-month tenor as realized skew collapsed "
            "following the January FOMC. Our model suggests put skew is now trading at its "
            "cheapest 30th percentile vs the prior 3-year window, offering selective "
            "opportunities for long downside gamma trades in size-adjusted structures.\n\n"
            "Term structure analysis shows the 1m/3m roll-down has compressed from 2.8 to "
            "1.4 vol points, indicating the market is pricing a flatter realized vol path "
            "into mid-year. Calendar spreads—long March/short June—carry a net positive "
            "theta of approximately $18k per vega unit for a $50M notional book. The "
            "1-year skew curve remains positively sloped, suggesting macro tail risk is "
            "being re-priced as a 2026 rather than 2025 event.\n\n"
            "Recommended trades: (1) Buy SPX 3m 95-strike put spreads vs selling 1m "
            "variance swaps at 18.4 to monetize the term structure mispricing. (2) Sell "
            "1m 110-strike calls in overwriter structures where clients are long the index "
            "above current fair value. Vol-of-vol (VVIX) at 87 suggests any gamma "
            "acceleration from a vol shock remains contained in the near term."
        ),
        "citations": ["Gatheral (2006)", "Carr-Wu (2016)", "Internal: VOL-2024-031"],
    },
    # ------------------------------------------------------------------ #
    # 2. IV-RV spread study
    # ------------------------------------------------------------------ #
    {
        "id": "VOL-2025-002",
        "title": "Implied vs Realized Volatility Spread: Persistent Richness in Large-Cap Tech",
        "author": "James Okafor",
        "date": "2025-01-28",
        "tags": ["IV-RV", "volatility premium", "mega-cap tech", "variance swap"],
        "desk_relevance": ["vol", "equities"],
        "content": (
            "Rolling 30-day IV minus RV spreads for the Mag-7 cluster averaged +4.8 vol "
            "points in Q4 2024, compared to a 5-year historical mean of +3.1. NVDA drove "
            "the bulk of the divergence, where 30-day IV ran at 52 vs 41 realized—a spread "
            "of 11 points. MSFT, GOOGL, and META each exhibited spreads between 3 and 5 "
            "points, consistent with structural demand for downside protection from "
            "systematic overwriters and 0DTE participants.\n\n"
            "Variance swap entry levels for the 1-month tenor are tracking 11–14 variance "
            "points rich in NVDA, TSLA, and AMZN vs a fair-value model calibrated on "
            "realized vol, vol-of-vol, and earnings event frequency. This richness persists "
            "despite multiple periods of elevated realized vol in late 2024, suggesting "
            "structural bid—potentially related to leveraged note issuance and structured "
            "product hedging flows.\n\n"
            "Key finding: Selling 1m variance in NVDA vs buying 1m variance in NDX "
            "(dispersion trade) shows a Sharpe of 1.6 over 36 months, with maximum "
            "drawdown of -2.1 vol points during the August 2024 yen carry unwind. This "
            "structure warrants re-entry at current levels with a 6-month conviction."
        ),
        "citations": ["Neuberger (1994)", "Demeterfi et al. (1999)", "Internal: VOL-2024-018"],
    },
    # ------------------------------------------------------------------ #
    # 3. Earnings volatility
    # ------------------------------------------------------------------ #
    {
        "id": "EQ-2025-003",
        "title": "Q1 2025 Earnings Season: Expected Moves vs Realized—Post-Mortem",
        "author": "Priya Nair",
        "date": "2025-02-20",
        "tags": ["earnings", "straddle", "expected move", "single stock vol"],
        "desk_relevance": ["equities", "vol"],
        "content": (
            "Across 187 S&P 500 names reporting in the January earnings window, the ratio "
            "of straddle-implied move to subsequent 1-day realized move averaged 1.18x—"
            "meaning options overpriced the earnings reaction by 18% on average. This is "
            "broadly consistent with the long-run historical ratio of 1.15–1.20x, reaffirming "
            "the structural edge in short earnings vol for well-diversified portfolios.\n\n"
            "Notable outliers where realized exceeded implied: SMCI (+6.1 standard deviations "
            "above its implied move), LYFT (+4.3), and ANET (+3.1). SMCI's miss was driven "
            "by a surprise accounting restatement—classic idiosyncratic tail not captured "
            "by vol models. Fading earnings vol in mega-cap tech (AAPL, MSFT, AMZN) "
            "produced an average P&L of +0.9 vol points per contract, in line with recent "
            "quarters.\n\n"
            "Recommendation: Maintain systematic short-strangle overlay on large-cap names "
            "with liquid options markets and >$20B float. Hedge tail risk with OTM put "
            "spreads at 85-strike for names where single-stock risk is concentrated. IV "
            "crush efficiency (ratio of IV 1 day pre-earnings to IV close 1 day post) "
            "averaged 0.68 in Q1 2025, in line with Q4 2024 (0.71) and Q3 2024 (0.65)."
        ),
        "citations": ["Goyal-Saretto (2009)", "Internal: EQ-2024-041", "Internal: VOL-2024-022"],
    },
    # ------------------------------------------------------------------ #
    # 4. Sector dispersion
    # ------------------------------------------------------------------ #
    {
        "id": "EQ-2025-004",
        "title": "Sector Dispersion Analysis: Technology vs Financials vs Energy in Elevated Correlation Regimes",
        "author": "Marcus Delacroix",
        "date": "2025-03-01",
        "tags": ["dispersion", "correlation", "sector vol", "index vol"],
        "desk_relevance": ["equities", "vol", "macro"],
        "content": (
            "Index vol/sector vol ratios have compressed sharply since the February FOMC, "
            "with the SPX 1m implied vol at 15.2 vs the GDP-weighted average of sector "
            "implied vols at 19.8—a spread of 4.6 points that historically signals "
            "dispersion richness. The implied correlation derived from this spread sits at "
            "the 62nd percentile vs a 3-year range, below the threshold (75th) we typically "
            "require for a standalone dispersion long.\n\n"
            "Technology sector exhibits the highest intra-sector dispersion: the 1m "
            "cross-sectional vol of daily returns for the XLK constituents is 1.82% vs "
            "XLK itself at 0.94%, a dispersion ratio of 1.94x. This is consistent with "
            "continued AI-driven bifurcation between winners (NVDA, AVGO) and laggards "
            "(INTC, QCOM) within the sector. Energy shows the opposite: tight clustering "
            "around oil price moves with dispersion ratio of 1.12x.\n\n"
            "Trade structure: Long 1m variance on XLK constituents (market-cap weighted "
            "basket of top 10) vs short 1m variance on XLK ETF. Indicative carry cost is "
            "-0.3 vol points/month; expected break-even requires correlation to drop below "
            "0.58 from current 0.69. Catalyst: NVDA earnings (May) likely to re-widen "
            "dispersion materially."
        ),
        "citations": ["Deng (2008)", "Bossu (2007)", "Internal: EQ-2024-037"],
    },
    # ------------------------------------------------------------------ #
    # 5. Macro vol regime
    # ------------------------------------------------------------------ #
    {
        "id": "MACRO-2025-005",
        "title": "Macro Volatility Regimes: Identifying Regime Shifts Using VIX Term Structure and MOVE Index",
        "author": "Sofia Bernstein",
        "date": "2025-01-15",
        "tags": ["VIX", "MOVE", "regime", "macro", "cross-asset vol"],
        "desk_relevance": ["macro", "rates", "vol"],
        "content": (
            "Cross-asset vol regimes have historically clustered into four states: "
            "suppressed (VIX < 14, MOVE < 80), normal (VIX 14–20, MOVE 80–110), stressed "
            "(VIX 20–30, MOVE 110–140), and crisis (VIX > 30, MOVE > 140). We are "
            "currently in the normal regime with VIX at 17.3 and MOVE at 97.4. Transition "
            "probabilities from our HMM model suggest a 23% probability of entering the "
            "stressed regime within 60 days, elevated vs the unconditional 14%.\n\n"
            "The VIX 3m/6m futures spread (currently -1.4 pts) is a useful leading "
            "indicator of regime transitions. Historically, when this spread inverts below "
            "-2.0, the probability of a VIX spike >5 pts within 30 days rises to 41%. "
            "MOVE is exhibiting divergence from VIX—rates vol has stayed structurally "
            "elevated (MOVE 30-day average: 104) even as equity vol compressed, consistent "
            "with ongoing Fed policy uncertainty transmitting to the rates complex.\n\n"
            "Portfolio implications: Maintain long tail risk in the rates vol book via "
            "payer swaption structures (3m into 10y at 4.75% strike). Reduce equity vol "
            "short exposure to 70% of normal sizing pending clarity on March FOMC dot-plot "
            "revisions. Cross-asset correlation between equity and rates vol spikes has "
            "averaged 0.61 in stressed regimes—justify a modest cross-asset vol hedge."
        ),
        "citations": ["Hamilton (1989)", "Bates (1996)", "Internal: MACRO-2024-008"],
    },
    # ------------------------------------------------------------------ #
    # 6. Greek sensitivity
    # ------------------------------------------------------------------ #
    {
        "id": "VOL-2025-006",
        "title": "Second-Order Greek Sensitivities: Vanna and Volga Exposure in the SPX Book",
        "author": "Elena Marchetti",
        "date": "2025-02-28",
        "tags": ["vanna", "volga", "greeks", "vol book", "SPX"],
        "desk_relevance": ["vol"],
        "content": (
            "The vol desk's SPX book carries net vanna of -$1.2M per 1-vol-point move in "
            "spot vol combined with a 1% spot move—meaningfully short, reflecting our "
            "overwriter overlays. Vanna risk is concentrated in the 95-100 strike cluster "
            "of the March expiry, where long put positions held by counterparties drive "
            "our short vanna via the dealer books. This creates a self-reinforcing dynamic "
            "on vol sell-offs: as spot rises and vol falls simultaneously, our delta "
            "exposure increases, requiring re-hedging that can amplify moves.\n\n"
            "Volga (vol of vol sensitivity) is net long at $380K per 1-vol-point move in "
            "VVIX, predominantly from long 1m 110-strike calls held as upside gamma "
            "buffers. This long volga position partially offsets the short vanna book: "
            "stress tests show combined vanna/volga P&L ranges from -$4.1M (slow grind "
            "lower + rising vol) to +$2.8M (rapid drop + vol spike) in a 2-sigma "
            "scenario.\n\n"
            "Recommended adjustment: Reduce short vanna by buying 2,000 contracts of the "
            "95/97.5 put spread to re-center greek exposure. This costs approximately "
            "$340K in premium and reduces net vanna by $280K. Alternative: Enter a "
            "vanna-neutral variance swap position that isolates pure volga exposure—"
            "viable if we wish to maintain current delta/vega profile while managing the "
            "second-order book."
        ),
        "citations": ["Castagna-Mercurio (2007)", "Internal: VOL-2025-001"],
    },
    # ------------------------------------------------------------------ #
    # 7. Options flow analysis
    # ------------------------------------------------------------------ #
    {
        "id": "EQ-2025-007",
        "title": "Institutional Options Flow Patterns: Q1 2025 Order Flow Analysis and Positioning Signals",
        "author": "James Okafor",
        "date": "2025-03-05",
        "tags": ["options flow", "dark pool", "positioning", "institutional"],
        "desk_relevance": ["equities", "vol"],
        "content": (
            "Analysis of CBOE and OCC flow data for Q1 2025 reveals a significant shift "
            "toward longer-dated protective structures. The ratio of 6m+ put open interest "
            "to 1m put open interest hit 2.3x in March, the highest since Q4 2022. This "
            "reflects rotation away from short-dated 0DTE speculation toward longer-term "
            "macro hedges—consistent with commentary from institutional clients in our "
            "prime brokerage channel about extending hedge duration into Q3 2025.\n\n"
            "Unusual call activity was flagged in XLF (financials ETF): 47,000 contracts "
            "of 43-strike calls were bought in a single session on Feb 28, with 3-week "
            "expiry—a position costing approximately $1.1M in premium. Subsequent "
            "follow-through in the underlying (+2.3% in 4 days) suggests informed flow "
            "ahead of bank stress test expectations. Similar concentrated call buying was "
            "observed in VALE (iron ore exposure) and MPC (refinery margins play).\n\n"
            "Systematic signal: Our flow-based momentum model (calibrated on 6 months of "
            "ORATS data) generated a buy signal on QQQ 1m straddles on March 3rd; the "
            "subsequent move realized at 1.7x the implied move, confirming signal validity. "
            "Net result: Q1 YTD, flow-based signals contributed +$2.3M to the equities "
            "vol book, representing 18% of total P&L from systematic strategies."
        ),
        "citations": ["Easley et al. (1998)", "Pan-Poteshman (2006)", "Internal: EQ-2024-029"],
    },
    # ------------------------------------------------------------------ #
    # 8. Correlation breakdown
    # ------------------------------------------------------------------ #
    {
        "id": "MACRO-2025-008",
        "title": "Correlation Breakdown During Stress Events: Lessons from the August 2024 Yen Carry Unwind",
        "author": "Sofia Bernstein",
        "date": "2025-01-10",
        "tags": ["correlation", "stress", "yen carry", "cross-asset", "contagion"],
        "desk_relevance": ["macro", "vol", "rates"],
        "content": (
            "The August 5, 2024 yen carry unwind generated a correlation spike that caught "
            "most multi-asset books off-guard. Equity-bond correlation, typically negative "
            "(-0.35 rolling 60-day), inverted to +0.68 intraday as both SPX and UST "
            "sold off simultaneously. This breakdown was preceded by a 3-day window where "
            "JPY/USD cross-currency basis compressed by 28bps—a signal that was available "
            "in our data but not wired into our correlation regime model.\n\n"
            "Key finding: Diversification benefits collapsed from an expected portfolio "
            "volatility of 8.2% (model) to a realized 2-day vol of 14.7%—a 1.79x "
            "underestimation. The correlation between SPX vol and rates vol (VIX vs MOVE) "
            "spiked from 0.22 (normal regime) to 0.81 during the 5-day event window, "
            "amplifying the vol desk's cross-asset hedges in the wrong direction. Tail "
            "correlation between previously uncorrelated legs is the dominant undiversified "
            "risk in our current book.\n\n"
            "Remediation steps implemented: (1) Added JPY/USD basis as a real-time "
            "correlation regime indicator. (2) Introduced a stress correlation overlay "
            "that increases minimum assumed equity-rates correlation from -0.20 to +0.45 "
            "when JPY basis moves >5bps/day. (3) Incorporated cross-asset vol spike "
            "scenarios into monthly VaR backtests. Estimated impact: +$4.2M worst-case "
            "protection in equivalent August 2024 scenario."
        ),
        "citations": ["Longin-Solnik (2001)", "Ang-Chen (2002)", "Internal: MACRO-2024-014"],
    },
    # ------------------------------------------------------------------ #
    # 9. Rates vol
    # ------------------------------------------------------------------ #
    {
        "id": "RATES-2025-009",
        "title": "Swaption Volatility Surface Update: Front-End Richness and Long-End Cheapness",
        "author": "David Kowalski",
        "date": "2025-02-07",
        "tags": ["swaption", "rates vol", "MOVE", "curve", "SOFR"],
        "desk_relevance": ["rates", "macro"],
        "content": (
            "The swaption volatility surface shows significant richness in short expiries "
            "(1m–3m) relative to long expiries (1y–2y), driven by near-term FOMC "
            "uncertainty and CPI print sensitivity. 1m into 5y swaption vol stands at "
            "89bps normal vol vs the 1y into 5y at 68bps—a steepness ratio of 1.31x "
            "vs a 3-year average of 1.08x. This front-end richness creates an attractive "
            "entry for calendar spreads: short 1m/long 3m 5y swaption straddles.\n\n"
            "The SOFR OIS curve implies 2.3 cuts priced for 2025 following the January "
            "employment report. Our rates strategy team forecasts 1.5 cuts as the base "
            "case, suggesting front-end rates vol is pricing too much policy optionality. "
            "Gamma in 1m SOFR options has risen to 3.8 cents per basis point—elevated "
            "by historical standards and consistent with a market that is actively hedging "
            "event risk around each data release.\n\n"
            "Position update: The rates vol book is currently long 3m/5y receiver swaption "
            "at 4.40% (entered at 72bps vol, now 81bps—marked at +$2.1M unrealized). "
            "We recommend adding to this position on any vol mean-reversion toward 75bps, "
            "targeting an exit at 90bps with a stop at 68bps. The risk/reward is 2.5:1 "
            "based on current term structure shape."
        ),
        "citations": ["Rebonato (2002)", "Brigo-Mercurio (2006)", "Internal: RATES-2024-007"],
    },
    # ------------------------------------------------------------------ #
    # 10. Macro rates regime
    # ------------------------------------------------------------------ #
    {
        "id": "MACRO-2025-010",
        "title": "Fed Policy Uncertainty and Volatility Premium: A Regime Analysis 2022–2025",
        "author": "Sofia Bernstein",
        "date": "2025-03-10",
        "tags": ["Fed", "policy uncertainty", "vol premium", "macro regime"],
        "desk_relevance": ["macro", "rates", "vol"],
        "content": (
            "We analyze 36 months of options pricing data across equity, rates, and FX "
            "vol surfaces to understand how Fed policy uncertainty is reflected in vol "
            "premia. Using the FOMC Uncertainty Index (derived from Fed funds futures "
            "option spreads), we identify three distinct volatility premium regimes:\n\n"
            "Regime A (policy tightening, high uncertainty, 2022–early 2023): Average "
            "IV-RV spread for SPX = +7.2 vol pts, MOVE vol premium = +22bps. Excess vol "
            "premium was monetizable via systematic variance selling with 60-day Sharpe "
            "of 1.8. Regime B (pause/pivot expectations, 2023–mid 2024): Equity vol "
            "premium compressed to +3.1pts; rates vol premium fell to +9bps. The "
            "variance selling Sharpe dropped to 0.9. Regime C (current, 2024–present): "
            "Mixed signals—equity vol near fair value but rates vol structurally rich.\n\n"
            "Current regime C is characterized by a bifurcated vol premium landscape: "
            "selling equity vol near-term is modestly profitable (Sharpe 1.1) while "
            "rates vol overwriting is more attractive (Sharpe 1.7 in backtests). The "
            "risk is an unexpected Fed pivot (either direction) that collapses cross-"
            "asset correlation assumptions. We recommend a 60/40 portfolio of rates vol "
            "selling (60%) vs equity vol selling (40%) vs the previous quarter's 40/60 "
            "split."
        ),
        "citations": ["Baker et al. (2016)", "Bauer-Rudebusch (2023)", "Internal: MACRO-2024-011"],
    },
    # ------------------------------------------------------------------ #
    # 11. Credit vol
    # ------------------------------------------------------------------ #
    {
        "id": "MACRO-2025-011",
        "title": "CDX IG vs CDX HY Volatility Divergence: Spread Compression and Tail Hedging",
        "author": "Marcus Delacroix",
        "date": "2025-02-03",
        "tags": ["CDX", "credit vol", "IG", "HY", "credit spreads"],
        "desk_relevance": ["macro", "rates"],
        "content": (
            "CDX IG 5y spreads compressed to 48bps in January 2025, the tightest level "
            "since early 2022. Concurrently, CDX HY 5y sits at 285bps. The IG/HY spread "
            "ratio of 5.9x is near the low end of its 10-year range (5.5–9.2x), "
            "suggesting either HY is cheap or IG is expensive. Credit vol (measured by "
            "the implied vol of 3m options on CDX IG) remains compressed at 22% vs "
            "35% historical average, implying markets are pricing minimal credit event "
            "risk for investment-grade issuers.\n\n"
            "Our analysis of credit default swaption (CDSO) flows shows a marked increase "
            "in payer protection buying since February 1st, concentrated in financials "
            "(BAC, MS, GS) and BBB-rated industrials. This divergence between tight "
            "spreads and rising tail protection demand is a classic late-cycle signal "
            "that we have observed before credit episodes in 2007, 2015, and 2019.\n\n"
            "Portfolio recommendation: Add credit tail hedges via CDX IG payer swaptions "
            "(3m into 5y, 55bps strike) at a premium cost of approximately 18bps. "
            "This positions the book for a spread widening of >20bps within 90 days while "
            "capping downside to the premium paid. Pair with short IG vol (via credit "
            "variance selling) to fund the hedge at near-zero carry cost."
        ),
        "citations": ["Hull-White (2000)", "Schönbucher (2003)", "Internal: MACRO-2024-016"],
    },
    # ------------------------------------------------------------------ #
    # 12. Energy sector vol
    # ------------------------------------------------------------------ #
    {
        "id": "EQ-2025-012",
        "title": "Energy Sector Volatility: WTI-Linked Options Pricing and Geopolitical Risk Premium",
        "author": "Priya Nair",
        "date": "2025-02-18",
        "tags": ["energy", "WTI", "options", "geopolitical", "sector vol"],
        "desk_relevance": ["equities", "macro"],
        "content": (
            "WTI crude 1m ATM implied vol rose from 22% to 31% in the first two weeks of "
            "February following escalating Middle East shipping disruption news. The risk "
            "premium embedded in crude options (IV minus 30-day RV) expanded from the "
            "baseline +3 vol pts to +9 vol pts, the widest in 14 months. Historically, "
            "this level of risk premium expansion has reverted to mean within 4–6 weeks "
            "in the absence of a supply disruption materializing.\n\n"
            "Equity energy names (XOM, CVX, COP) showed a divergent vol response: "
            "implied vol rose modestly (+2–3 pts) while WTI vol spiked +9 pts, creating "
            "a structural basis opportunity. The regression of energy equity vol on WTI "
            "vol has a beta of 0.31 (R²=0.62 over 2 years), meaning energy equities "
            "priced only ~31% of the crude vol move. Selling WTI vol while buying "
            "energy equity vol captures this basis discrepancy.\n\n"
            "Trade recommendation: Long XOM 1m straddle at 26.5 vol vs short WTI 1m "
            "straddle at 31 vol in a beta-neutral ratio (3:1 WTI:XOM). Indicative entry "
            "premium: net credit of $42K per unit. Break-even: the basis needs to converge "
            "by at least 2 vol points. Historical mean reversion time: 18 trading days "
            "average."
        ),
        "citations": ["Trolle-Schwartz (2009)", "Internal: EQ-2024-033"],
    },
    # ------------------------------------------------------------------ #
    # 13. Realized vol forecasting
    # ------------------------------------------------------------------ #
    {
        "id": "VOL-2025-013",
        "title": "Forecasting 30-Day Realized Volatility: GARCH vs HAR vs LSTM Comparison",
        "author": "Elena Marchetti",
        "date": "2025-01-22",
        "tags": ["realized vol", "forecasting", "GARCH", "HAR", "machine learning"],
        "desk_relevance": ["vol", "equities"],
        "content": (
            "We evaluate three volatility forecasting models—GARCH(1,1), HAR-RV, and a "
            "bidirectional LSTM—across six equity indices (SPX, NDX, RUT, DAX, N225, HSI) "
            "over 24 months of out-of-sample testing ending December 2024. The HAR-RV "
            "model demonstrates the best aggregate performance: QLIKE loss of 0.41 vs "
            "0.48 for GARCH and 0.44 for LSTM. Crucially, HAR-RV is also interpretable—"
            "the daily, weekly, and monthly realized vol components each carry economically "
            "meaningful loadings (0.39, 0.31, 0.18 respectively for SPX).\n\n"
            "The LSTM model outperforms on RUT (Russell 2000) and HSI, where nonlinear "
            "regime dynamics are more pronounced. However, LSTM requires approximately "
            "18 months of retraining data to maintain calibration, making it operationally "
            "intensive. GARCH is the worst performer across all indices except during "
            "calm low-vol regimes where its simplicity is an advantage.\n\n"
            "Recommendation: Adopt HAR-RV as the primary forecasting model for the vol "
            "desk's daily P&L attribution and risk-of-loss calculations. Maintain the "
            "LSTM as a secondary signal for tail risk scenarios. Override both models "
            "with a 'fear premium' adjustment (+3 vol pts) when the VVIX/VIX ratio "
            "exceeds 5.5, a threshold associated with reflexive vol dynamics."
        ),
        "citations": ["Corsi (2009)", "Andersen et al. (2003)", "Internal: VOL-2024-028"],
    },
    # ------------------------------------------------------------------ #
    # 14. Gamma exposure
    # ------------------------------------------------------------------ #
    {
        "id": "VOL-2025-014",
        "title": "Dealer Gamma Exposure and Market Pinning: SPX Year-End and Quarterly Expiry Analysis",
        "author": "James Okafor",
        "date": "2025-01-05",
        "tags": ["gamma", "dealer positioning", "pinning", "expiry", "GEX"],
        "desk_relevance": ["vol", "equities"],
        "content": (
            "Dealer gamma exposure (GEX) analysis at the December 2024 quarterly expiry "
            "showed net dealer long gamma of +$4.8B/1% move for SPX, the largest long "
            "gamma position since March 2023. This created strong pinning dynamics: "
            "SPX traded within a 35-point range for the final 8 days of December, vs "
            "a 60-point range in the equivalent 2023 period. Our GEX model correctly "
            "predicted the 4765-4800 pin zone with 78% accuracy across the final week.\n\n"
            "The mechanism: when dealers are long gamma, they sell into rallies and buy "
            "into dips to maintain delta neutrality, dampening realized vol. Conversely, "
            "when net short gamma, dealers amplify moves. The transition from net long "
            "to net short GEX at any given level functions as a 'vol zone' where realized "
            "vol can spike abruptly. Currently, the SPX net gamma flip level is "
            "approximately 5,020 (based on March expiry open interest).\n\n"
            "Trading implication: Below 5,020, we expect damped SPX vol and mean-reverting "
            "intraday moves—favorable for short straddle strategies. Above 5,020, expect "
            "increased realized vol as dealer short-gamma amplifies moves—shift exposure "
            "to long gamma or reduce short vol notional by 40%."
        ),
        "citations": ["Gârleanu et al. (2009)", "Muravyev (2016)", "Internal: VOL-2024-035"],
    },
    # ------------------------------------------------------------------ #
    # 15. FX vol
    # ------------------------------------------------------------------ #
    {
        "id": "MACRO-2025-015",
        "title": "FX Volatility Clusters: EUR/USD and USD/JPY Implied Vol Dynamics in Carry Regimes",
        "author": "David Kowalski",
        "date": "2025-02-25",
        "tags": ["FX vol", "EURUSD", "USDJPY", "carry", "risk reversal"],
        "desk_relevance": ["macro", "rates"],
        "content": (
            "EUR/USD 1m implied vol has compressed to 6.8% from a peak of 9.4% in October "
            "2024, while USD/JPY 1m implied vol remains elevated at 11.2%—more than 4 "
            "vol points of cross-pair divergence. This divergence reflects differential "
            "central bank uncertainty: ECB rate path is largely priced (2 cuts by year- "
            "end, high confidence), while BOJ normalization timing remains contested.\n\n"
            "EUR/USD 25-delta risk reversals are currently at -0.4 (slight dollar demand), "
            "consistent with muted tail risk perception. USD/JPY risk reversals stand at "
            "+1.9 (yen put demand, i.e., yen depreciation hedging). The asymmetry in "
            "carry demand is visible in 3-month implied vol term structure: EUR/USD is "
            "flat (6.8% vs 6.9% for 3m), while USD/JPY is inverted (11.2% vs 10.4% for "
            "3m), suggesting the near-term yen risk is more acute than the medium-term.\n\n"
            "Position recommendation: Long USD/JPY 1m 25-delta straddle at 11.2% as a "
            "macro vol hedge—provides convex payout in either a BOJ surprise hike or a "
            "sharp yen weakening scenario. Pair with short EUR/USD gamma (sell 1m ATM "
            "straddle at 6.8%) to fund approximately 60% of the premium. Net cost: "
            "$290K per $100M notional with break-even at ±1.8% USD/JPY move."
        ),
        "citations": ["Garman-Kohlhagen (1983)", "Carr-Wu (2007)", "Internal: MACRO-2024-013"],
    },
    # ------------------------------------------------------------------ #
    # 16. Vol surface calibration
    # ------------------------------------------------------------------ #
    {
        "id": "VOL-2025-016",
        "title": "SVI Parameterization and Arbitrage-Free Surface Construction: Methodology Update",
        "author": "Elena Marchetti",
        "date": "2025-03-12",
        "tags": ["SVI", "vol surface", "calibration", "arbitrage-free", "methodology"],
        "desk_relevance": ["vol"],
        "content": (
            "We document an update to our vol surface calibration methodology following "
            "identification of calendar spread arbitrage violations in the 2-week/1-month "
            "sector of the SPX vol surface on high-vol days. The prior parameterization "
            "used independent SVI fits per expiry, which can violate no-calendar-spread "
            "arbitrage conditions when vol rises sharply and the surface reprices rapidly.\n\n"
            "The updated methodology applies a joint SVI calibration across all listed "
            "expiries (2 weeks to 12 months), imposing total variance monotonicity as a "
            "hard constraint. The Nelder-Mead optimizer was replaced with a "
            "gradient-descent solver with analytical Jacobian, reducing calibration time "
            "from 1.4s to 0.18s per surface update—critical for intraday risk management "
            "during fast market conditions. Backtest across 500 SPX trading days shows "
            "zero calendar arbitrage violations vs 23 in the prior approach.\n\n"
            "The butterfly arbitrage check (Breedon-Litvinova condition) now runs "
            "automatically post-calibration; if any violation is detected, the strike "
            "interpolation reverts to a cubic spline fallback for the affected expiry "
            "slice. This ensures the pricing library never outputs negative local variance "
            "densities. The update is live in production as of February 28, 2025."
        ),
        "citations": ["Gatheral-Jacquier (2014)", "Breedon-Litvinova (2022)", "Internal: VOL-2024-039"],
    },
    # ------------------------------------------------------------------ #
    # 17. Earnings dispersion
    # ------------------------------------------------------------------ #
    {
        "id": "EQ-2025-017",
        "title": "Cross-Sector Earnings Dispersion Trades: Optimizing the Long/Short Vol Ratio",
        "author": "Priya Nair",
        "date": "2025-03-08",
        "tags": ["earnings", "dispersion", "cross-sector", "vol ratio", "single stock"],
        "desk_relevance": ["equities", "vol"],
        "content": (
            "We analyze 48 cross-sector earnings dispersion trades executed over the past "
            "4 quarters, defined as long individual stock straddle/short ETF straddle "
            "combinations timed around earnings. The mean realized P&L per trade was "
            "+$47K with a standard deviation of $198K, yielding a Sharpe of 0.24 per "
            "trade. However, when filtered to only trades where the implied move / "
            "historical earnings move ratio exceeded 1.15x for the single stock AND the "
            "ETF IV-RV spread was above its 70th percentile, the Sharpe improved to 0.91.\n\n"
            "Key finding: The signal degrades sharply when sector correlation is above 0.75 "
            "(dispersion trades tend to pay off less when stocks move together). The XLK "
            "correlation regime was the most problematic in Q3 2024, where broad-based "
            "tech selling drove correlation to 0.82 and hurt 7 of 9 dispersion structures. "
            "In contrast, Q1 2025 saw correlation at 0.58 and 12 of 14 trades positive.\n\n"
            "Process improvement: Implement a correlation filter that gates entry to trades "
            "when 21-day sector correlation is below 0.70. This would have eliminated the "
            "7 Q3 2024 losers while retaining all of Q1 2025's winners. Expected impact "
            "on strategy Sharpe: improvement from 0.91 to 1.34 based on backtesting."
        ),
        "citations": ["Deng-Reghai (2015)", "Internal: EQ-2025-004", "Internal: EQ-2025-003"],
    },
    # ------------------------------------------------------------------ #
    # 18. Tail risk
    # ------------------------------------------------------------------ #
    {
        "id": "MACRO-2025-018",
        "title": "Tail Risk Hedging Framework: Cost-Efficient Convexity for Multi-Asset Portfolios",
        "author": "Marcus Delacroix",
        "date": "2025-01-30",
        "tags": ["tail risk", "hedge", "convexity", "VaR", "multi-asset"],
        "desk_relevance": ["macro", "vol", "equities"],
        "content": (
            "This note establishes a framework for evaluating tail risk hedge efficiency "
            "across five instrument types: OTM equity puts, VIX call spreads, payer "
            "swaptions, gold calls, and FX safe-haven structures (long JPY calls). We "
            "measure efficiency as the ratio of expected P&L in a 3-sigma stress scenario "
            "to the carry cost (premium decay) per unit time.\n\n"
            "Results over 10 stress episodes since 2018: VIX call spreads (20/30) show "
            "the highest efficiency ratio of 8.4x (mean $10.9M payout vs $1.3M carry "
            "cost), but exhibit path dependency—require the VIX spike to happen within "
            "the option window. Gold calls (3m, 5% OTM) have an efficiency ratio of "
            "5.1x with lower path dependency. OTM equity puts (3m, 10% OTM) show 4.3x "
            "but are subject to term structure drag if the hedge must be rolled.\n\n"
            "Optimal hedge basket for a $500M multi-asset book: 35% VIX call spreads, "
            "30% OTM equity puts, 20% gold calls, 15% yen calls. Total carry cost: "
            "approximately $3.8M/year (76bps of AUM). This basket delivered $41.2M in "
            "the August 2024 stress event vs a standalone 5% equity put portfolio of "
            "$24.1M—a 71% improvement for the same carry budget."
        ),
        "citations": ["Bhansali (2014)", "Spitznagel (2013)", "Internal: MACRO-2024-018"],
    },
    # ------------------------------------------------------------------ #
    # 19. Liquidity and microstructure
    # ------------------------------------------------------------------ #
    {
        "id": "EQ-2025-019",
        "title": "Options Market Microstructure: Bid-Ask Spread Dynamics and Execution Cost Analysis",
        "author": "James Okafor",
        "date": "2025-02-12",
        "tags": ["microstructure", "bid-ask spread", "execution", "liquidity", "market impact"],
        "desk_relevance": ["equities", "vol"],
        "content": (
            "We conduct a systematic analysis of SPX and SPY options execution quality "
            "across 60 trading days (November 2024–January 2025). The mean bid-ask spread "
            "as a percentage of mid-price for ATM SPX options is 0.38% for 1-month expiries, "
            "widening to 0.81% for 3-month expiries and 1.42% for 6-month expiries. This "
            "term-structure widening of relative spreads is partly attributable to reduced "
            "quote competition from electronic market makers beyond the 90-day horizon.\n\n"
            "Execution timing analysis shows significant intraday variation: the first 30 "
            "minutes post-open and the last 30 minutes pre-close carry 23% and 18% wider "
            "spreads respectively vs the 11am–1pm mid-day window. For the vol desk's "
            "rolling structures, timing execution to avoid the open/close windows and "
            "executing between 10:30am–11:30am reduces realized slippage by approximately "
            "0.22 vol points per trade—meaningful for systematic strategies.\n\n"
            "Key finding: NBBO improvement rates for SPX options are 31% when using "
            "limit orders with a 5-minute patience window, vs 12% for market orders. "
            "Switching from market to limit orders for non-urgent delta hedges would "
            "reduce annual execution costs by an estimated $1.7M based on current "
            "trading volumes. Recommendation: update execution protocols for non-urgent "
            "option rolls to use aggressive limit orders with a 10-minute fill window."
        ),
        "citations": ["Black (1976)", "Cho-Engle (1999)", "Internal: EQ-2024-048"],
    },
    # ------------------------------------------------------------------ #
    # 20. Vol risk premium
    # ------------------------------------------------------------------ #
    {
        "id": "VOL-2025-020",
        "title": "Volatility Risk Premium Decomposition: Information, Hedging Demand, and Sentiment Components",
        "author": "Sofia Bernstein",
        "date": "2025-03-06",
        "tags": ["vol risk premium", "VRP", "hedging demand", "sentiment", "decomposition"],
        "desk_relevance": ["vol", "equities", "macro"],
        "content": (
            "We decompose the equity volatility risk premium (VRP) into three structural "
            "components using a signal extraction framework: (1) information component—"
            "reflecting genuine uncertainty about future realized vol, (2) hedging demand "
            "component—driven by the structural bid for protective options, and (3) "
            "sentiment component—noise and speculative positioning. Over the past 3 years, "
            "the average VRP of +3.8 vol pts decomposed as: information (1.1 pts), hedging "
            "demand (2.1 pts), and sentiment (0.6 pts).\n\n"
            "The hedging demand component is the most persistent and monetizable—it "
            "reflects structural insurance buying by leveraged funds, index trackers, and "
            "retail products. The sentiment component is the most mean-reverting and "
            "strongest driver of short-term VRP movements; sentiment-driven VRP expansion "
            "typically reverts within 15–20 trading days. Importantly, the sentiment "
            "component accounted for 78% of the August 2024 VRP spike to +9.2 pts, "
            "consistent with panic-driven option buying rather than rational re-hedging.\n\n"
            "Investment implications: Vol selling strategies should have higher conviction "
            "when the sentiment component is elevated (>1.5 pts above baseline). A "
            "regime-conditioned variance selling approach that targets only high-sentiment "
            "environments would have generated a Sharpe of 2.1 over the sample period, "
            "vs 1.3 for an unconditional approach. We will integrate this decomposition "
            "into the vol desk's daily morning brief starting Q2 2025."
        ),
        "citations": ["Bollerslev et al. (2009)", "Dew-Becker et al. (2017)", "Internal: VOL-2025-002"],
    },
]

# ---------------------------------------------------------------------------
# Index for fast lookup
# ---------------------------------------------------------------------------

_DOC_INDEX: dict[str, dict] = {doc["id"]: doc for doc in DOCUMENTS}


# ---------------------------------------------------------------------------
# Search helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """Lowercase word tokenizer — strips punctuation."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _build_tf(tokens: list[str]) -> dict[str, float]:
    """Term-frequency map (normalized by document length)."""
    freq: dict[str, int] = {}
    for tok in tokens:
        freq[tok] = freq.get(tok, 0) + 1
    n = max(len(tokens), 1)
    return {k: v / n for k, v in freq.items()}


def _idf_weight(term: str) -> float:
    """Simple pseudo-IDF: log(1 + N/df) where df = number of docs containing term."""
    df = sum(1 for doc in DOCUMENTS if term in doc["_tokens"])
    n = len(DOCUMENTS)
    if df == 0:
        return 0.0
    return math.log(1 + n / df)


# Pre-compute token lists and TF maps once at module load
for _doc in DOCUMENTS:
    _doc["_tokens"] = _tokenize(
        " ".join([_doc["title"], _doc["content"], " ".join(_doc["tags"])])
    )
    _doc["_tf"] = _build_tf(_doc["_tokens"])


def keyword_search(
    query: str,
    max_results: int = 5,
    desk_filter: Optional[list[str]] = None,
) -> list[dict]:
    """
    Return up to *max_results* documents ranked by TF-IDF cosine similarity.

    Parameters
    ----------
    query:
        Natural-language or keyword search string.
    max_results:
        Maximum number of results to return.
    desk_filter:
        If provided, only return documents whose desk_relevance overlaps.

    Returns a list of dicts with keys:
        doc_id, title, relevance_score, snippet, author, date, tags
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    # Build query TF
    q_tf = _build_tf(query_tokens)

    scores: list[tuple[float, dict]] = []
    for doc in DOCUMENTS:
        # Optional desk filter
        if desk_filter:
            if not any(d in doc["desk_relevance"] for d in desk_filter):
                continue

        # TF-IDF dot product (cosine without magnitude normalisation — simple demo)
        score = 0.0
        for term, qtf in q_tf.items():
            idf = _idf_weight(term)
            dtf = doc["_tf"].get(term, 0.0)
            score += qtf * idf * dtf

        if score > 0:
            scores.append((score, doc))

    scores.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, doc in scores[:max_results]:
        # Extract a snippet: first sentence containing a query token, or first 200 chars
        snippet = _extract_snippet(doc["content"], query_tokens)
        results.append(
            {
                "doc_id": doc["id"],
                "title": doc["title"],
                "relevance_score": round(score, 4),
                "snippet": snippet,
                "author": doc["author"],
                "date": doc["date"],
                "tags": doc["tags"],
            }
        )

    return results


def _extract_snippet(content: str, query_tokens: list[str]) -> str:
    """Return first sentence containing any query token, else first 200 chars."""
    sentences = re.split(r"(?<=[.!?])\s+", content)
    token_set = set(query_tokens)
    for sentence in sentences:
        if any(tok in _tokenize(sentence) for tok in token_set):
            return sentence[:220]
    return content[:200]


def get_document_by_id(doc_id: str) -> Optional[dict]:
    """
    Retrieve a full document by its ID.

    Returns the document dict (without internal _tokens/_tf keys),
    or None if not found.
    """
    doc = _DOC_INDEX.get(doc_id)
    if doc is None:
        return None
    return {k: v for k, v in doc.items() if not k.startswith("_")}


def all_document_ids() -> list[str]:
    """Return list of all document IDs."""
    return list(_DOC_INDEX.keys())
