"""
Thesis Validation Orchestrator — FastMCP server (port 8014).

Exposes a single tool:
  validate_thesis(thesis, desk, detail_level, ctx) -> dict

The tool runs the full 4-stage pipeline:
  1. Parser   — parse natural-language thesis into ThesisStatement
  2. Planner  — generate ValidationPlan from ThesisStatement
  3. Executor — execute plan against MCP gateway (Bloomberg, Risk, Research)
  4. Synthesiser — score evidence, assess risk, generate ValidationReport

Authentication: BearerAuthProvider validates Keycloak-issued JWTs.
The orchestrator uses its own client-credentials grant to call the gateway.

Entrypoint:
    python -m orchestrator.main
"""

from __future__ import annotations

import os
import time
from typing import Literal

import structlog
from mcp.server.fastmcp import Context, FastMCP

from .executor.gateway_client import GatewayClient
from .executor.plan_executor import execute_plan
from .parser.thesis_parser import parse_thesis
from .planner.plan_generator import generate_plan
from .synthesiser.report_generator import generate_report

log = structlog.get_logger("orchestrator.main")

# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

# ---------------------------------------------------------------------------
# Server setup
# ---------------------------------------------------------------------------

_KEYCLOAK_REALM_URL = os.environ.get(
    "KEYCLOAK_REALM_URL", "http://keycloak:8080/realms/trading"
)

# The orchestrator validates incoming requests with its own bearer auth.
# Downstream calls to the gateway use a separate client-credentials grant.
try:
    from mcp.server.auth.provider import BearerAuthProvider

    _auth = BearerAuthProvider(
        jwks_url=f"{_KEYCLOAK_REALM_URL}/protocol/openid-connect/certs",
        issuer=_KEYCLOAK_REALM_URL,
        audience="thesis-validator",
        required_scopes=["thesis:validate"],
    )
except Exception:
    # Auth provider unavailable in local dev without Keycloak — run unauthenticated
    _auth = None  # type: ignore[assignment]

mcp = FastMCP(
    name="thesis-validator",
    instructions=(
        "Investment thesis validation orchestrator. "
        "Validates natural-language investment theses by orchestrating calls to "
        "Bloomberg (market data), Risk (VaR, Greeks, scenarios), and Research "
        "(analyst notes) MCP servers through the central gateway. "
        "Returns a structured evidence report with FOR/AGAINST classifications, "
        "risk assessment, overall confidence score, and suggested refinements. "
        "Requires thesis:validate scope."
    ),
    auth=_auth,
)

# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


@mcp.tool()
async def validate_thesis(
    thesis: str,
    desk: str,
    detail_level: Literal["summary", "full"],
    ctx: Context,
) -> dict:
    """
    Validate an investment thesis against live market data, risk analytics,
    and analyst research.

    Runs a 4-stage pipeline:
      1. Parse the natural-language thesis into a structured claim.
      2. Generate a tailored validation plan (tool call sequence).
      3. Execute the plan against Bloomberg, Risk, and Research MCP servers.
      4. Synthesise evidence into a scored report with FOR/AGAINST/NEUTRAL items.

    USE THIS FOR:
      - Rapid pre-trade thesis validation before risk committee submission
      - Stress-testing directional assumptions against current market data
      - Generating structured evidence for trade proposals

    DO NOT USE FOR:
      - Order execution or trade blotter updates
      - Regulatory reporting or official risk sign-off
      - Real-time streaming data (results are point-in-time snapshots)

    Args:
        thesis:       Natural-language investment thesis. Examples:
                      "AAPL implied vol is mispriced relative to realised.
                       30-day IV-RV spread at 95th percentile."
                      "Tech sector showing momentum divergence from SPX. RSI overbought."
                      "Investment grade credit spreads are too tight. Mean reversion expected."
        desk:         Trading desk running the thesis: "equities", "rates", "vol",
                      "macro", or "credit".
        detail_level: "summary" returns verdict + confidence + top evidence only.
                      "full" returns the complete report including markdown.
        ctx:          MCP context carrying JWT auth claims.

    Returns:
        dict with keys:
          verdict       : "SUPPORTED" | "UNSUPPORTED" | "INCONCLUSIVE"
          confidence    : float 0–1
          risk_score    : "LOW" | "MEDIUM" | "HIGH" | "EXTREME"
          evidence_for  : list of evidence items supporting the thesis
          evidence_against: list of evidence items contradicting the thesis
          risk_assessment : risk dimensions dict
          refinements   : list of suggested improvements
          tool_calls_made : int
          total_latency_ms: float
          markdown_summary: full report (only when detail_level="full")
    """
    pipeline_start = time.monotonic()

    log.info(
        "validate_thesis_start",
        desk=desk,
        detail_level=detail_level,
        thesis_length=len(thesis),
    )

    # Stage 1: Parse
    parsed = parse_thesis(thesis)

    if not parsed.testable:
        return {
            "verdict": "INCONCLUSIVE",
            "confidence": 0.0,
            "risk_score": "UNKNOWN",
            "error": parsed.untestable_reason,
            "evidence_for": [],
            "evidence_against": [],
            "evidence_neutral": [],
            "risk_assessment": {},
            "refinements": [parsed.untestable_reason or "Refine the thesis to identify a specific instrument."],
            "tool_calls_made": 0,
            "total_latency_ms": 0.0,
            "markdown_summary": "",
            "parse": {
                "asset": parsed.asset,
                "claim_type": parsed.claim_type.value,
                "parse_confidence": parsed.parse_confidence,
            },
        }

    # Stage 2: Plan
    plan = generate_plan(parsed, desk)

    # Stage 3: Execute
    async with GatewayClient() as client:
        results = await execute_plan(plan, client, allow_partial_failure=True)

    total_latency_ms = (time.monotonic() - pipeline_start) * 1000

    # Stage 4: Synthesise
    report = generate_report(parsed, results, total_latency_ms)

    log.info(
        "validate_thesis_complete",
        verdict=report.verdict,
        confidence=report.confidence,
        risk_score=report.risk_assessment.risk_score,
        total_latency_ms=round(total_latency_ms, 1),
    )

    # Build response dict
    response: dict = {
        "verdict": report.verdict,
        "confidence": report.confidence,
        "risk_score": report.risk_assessment.risk_score,
        "evidence_for": [e.model_dump() for e in report.evidence_for],
        "evidence_against": [e.model_dump() for e in report.evidence_against],
        "evidence_neutral": [e.model_dump() for e in report.evidence_neutral],
        "risk_assessment": report.risk_assessment.model_dump(),
        "refinements": report.refinements,
        "tool_calls_made": report.tool_calls_made,
        "tool_calls_succeeded": report.tool_calls_succeeded,
        "total_latency_ms": round(total_latency_ms, 1),
        "parse": {
            "asset": parsed.asset,
            "asset_class": parsed.asset_class.value,
            "claim_type": parsed.claim_type.value,
            "direction": parsed.direction.value,
            "magnitude": parsed.magnitude,
            "timeframe": parsed.timeframe,
            "proposed_trade": parsed.proposed_trade,
            "parse_confidence": parsed.parse_confidence,
        },
    }

    if detail_level == "full":
        response["markdown_summary"] = report.markdown_summary

    return response


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    log.info("thesis_validator_starting", host="0.0.0.0", port=8014, path="/mcp")
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8014,
        path="/mcp",
    )


if __name__ == "__main__":
    main()
