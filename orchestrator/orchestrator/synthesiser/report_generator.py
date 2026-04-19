"""
Report Generator — assembles a ValidationReport from evidence and risk data.

Takes the raw evidence items and risk assessment and produces:
  1. A structured ValidationReport (Pydantic model / dict)
  2. A markdown-formatted analyst note embedded in the report

Verdict logic:
  - SUPPORTED     : weighted evidence confidence FOR > 0.55 AND
                    more FOR items than AGAINST items
  - UNSUPPORTED   : weighted evidence confidence FOR < 0.35 OR
                    AGAINST items outnumber FOR items by 2:1
  - INCONCLUSIVE  : everything else
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog

from ..executor.models import ToolCallResult
from ..parser.models import ThesisStatement
from .evidence_scorer import score_evidence
from .models import EvidenceItem, RiskAssessment, ValidationReport
from .risk_assessor import assess_risk

log = structlog.get_logger("orchestrator.synthesiser.report_generator")

# Refinement suggestions keyed on risk score
_RISK_REFINEMENTS: dict[str, list[str]] = {
    "EXTREME": [
        "Consider reducing position size to 25–50% of initial target given extreme tail risk.",
        "Add explicit stop-loss levels to the trade structure before execution.",
        "Seek second opinion from Risk Management before proceeding.",
    ],
    "HIGH": [
        "Size the position conservatively — start at 50% of target and scale in.",
        "Define maximum holding period and exit criteria upfront.",
        "Consider using options to cap downside rather than an outright position.",
    ],
    "MEDIUM": [
        "Standard position sizing applies; monitor mark-to-market daily.",
        "Set a pre-defined review trigger if the thesis assumptions change materially.",
    ],
    "LOW": [
        "Risk profile is favourable — standard execution guidelines apply.",
    ],
}

# Refinements for inconclusive verdicts
_INCONCLUSIVE_REFINEMENTS = [
    "Gather additional data: extend the lookback window to capture a full market cycle.",
    "Quantify the magnitude claim more precisely (e.g. exact spread percentile, z-score).",
    "Consider a smaller pilot position while waiting for the catalyst to emerge.",
]


def generate_report(
    thesis: ThesisStatement,
    results: list[ToolCallResult],
    total_latency_ms: float,
) -> ValidationReport:
    """
    Generate a complete ValidationReport from executor results.

    Args:
        thesis:            Parsed thesis statement.
        results:           All ToolCallResults from the executor.
        total_latency_ms:  Wall-clock time of the full pipeline (ms).

    Returns:
        ValidationReport with all fields populated, including markdown_summary.
    """
    evidence = score_evidence(results, thesis)
    risk = assess_risk(results)

    for_items = [e for e in evidence if e.classification == "FOR"]
    against_items = [e for e in evidence if e.classification == "AGAINST"]
    neutral_items = [e for e in evidence if e.classification == "NEUTRAL"]

    confidence = _compute_confidence(for_items, against_items, neutral_items)
    verdict = _compute_verdict(for_items, against_items, confidence)
    refinements = _compute_refinements(verdict, risk, thesis)

    succeeded = sum(1 for r in results if r.success)

    report = ValidationReport(
        thesis_raw=thesis.raw_text,
        asset=thesis.asset,
        claim_type=thesis.claim_type.value,
        verdict=verdict,
        confidence=confidence,
        evidence_for=for_items,
        evidence_against=against_items,
        evidence_neutral=neutral_items,
        risk_assessment=risk,
        refinements=refinements,
        tool_calls_made=len(results),
        tool_calls_succeeded=succeeded,
        total_latency_ms=total_latency_ms,
        markdown_summary="",
    )

    report = report.model_copy(
        update={"markdown_summary": _render_markdown(report, thesis)}
    )

    log.info(
        "report_generated",
        verdict=verdict,
        confidence=round(confidence, 3),
        evidence_for=len(for_items),
        evidence_against=len(against_items),
        evidence_neutral=len(neutral_items),
        risk_score=risk.risk_score,
        tool_calls_made=len(results),
        tool_calls_succeeded=succeeded,
    )

    return report


# ---------------------------------------------------------------------------
# Verdict and confidence
# ---------------------------------------------------------------------------

def _compute_confidence(
    for_items: list[EvidenceItem],
    against_items: list[EvidenceItem],
    neutral_items: list[EvidenceItem],
) -> float:
    """
    Compute overall confidence as a weighted average of evidence confidences.

    FOR items contribute positively; AGAINST items contribute their weight
    as a drag on the FOR signal; NEUTRAL items are informational and
    contribute a small positive baseline.
    """
    all_items = for_items + against_items + neutral_items
    if not all_items:
        return 0.50

    # Weighted mean of FOR confidences
    if for_items:
        for_confidence = sum(e.confidence for e in for_items) / len(for_items)
    else:
        for_confidence = 0.0

    # Drag from AGAINST items
    if against_items:
        against_drag = sum(e.confidence for e in against_items) / len(against_items)
        # Weight: FOR items have 60% influence, AGAINST items have 40%
        n_for = len(for_items)
        n_against = len(against_items)
        total = n_for + n_against
        blended = (for_confidence * n_for - against_drag * n_against * 0.5) / total
    else:
        blended = for_confidence

    # Neutral items nudge toward 0.5 (reduce certainty slightly)
    if neutral_items:
        neutral_pull = 0.50
        neutral_weight = min(0.20, len(neutral_items) * 0.05)
        blended = blended * (1 - neutral_weight) + neutral_pull * neutral_weight

    return round(max(0.0, min(1.0, blended)), 3)


def _compute_verdict(
    for_items: list[EvidenceItem],
    against_items: list[EvidenceItem],
    confidence: float,
) -> str:
    n_for = len(for_items)
    n_against = len(against_items)

    if confidence >= 0.55 and n_for > n_against:
        return "SUPPORTED"
    if confidence < 0.35 or (n_against >= 2 and n_against >= n_for * 2):
        return "UNSUPPORTED"
    return "INCONCLUSIVE"


def _compute_refinements(
    verdict: str,
    risk: RiskAssessment,
    thesis: ThesisStatement,
) -> list[str]:
    refinements: list[str] = []

    if verdict == "INCONCLUSIVE":
        refinements.extend(_INCONCLUSIVE_REFINEMENTS)

    refinements.extend(_RISK_REFINEMENTS.get(risk.risk_score, []))

    if not thesis.testable and thesis.untestable_reason:
        refinements.append(f"Improve testability: {thesis.untestable_reason}")

    if thesis.proposed_trade is None:
        refinements.append(
            "Specify a concrete trade structure (e.g. long straddle, risk reversal) "
            "to enable more precise Greeks and scenario analysis."
        )

    return refinements


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _render_markdown(report: ValidationReport, thesis: ThesisStatement) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    verdict_emoji = {"SUPPORTED": "SUPPORTED", "UNSUPPORTED": "UNSUPPORTED", "INCONCLUSIVE": "INCONCLUSIVE"}
    verdict_label = verdict_emoji.get(report.verdict, report.verdict)

    risk = report.risk_assessment
    confidence_pct = f"{report.confidence * 100:.0f}%"

    lines: list[str] = [
        f"# Thesis Validation Report",
        f"",
        f"**Generated:** {ts}  ",
        f"**Asset:** {report.asset}  ",
        f"**Claim Type:** {report.claim_type.replace('_', ' ').title()}  ",
        f"**Verdict:** {verdict_label}  ",
        f"**Confidence:** {confidence_pct}  ",
        f"**Risk Score:** {risk.risk_score}  ",
        f"",
        f"---",
        f"",
        f"## Thesis",
        f"",
        f"> {report.thesis_raw}",
        f"",
    ]

    if thesis.proposed_trade:
        lines += [
            f"**Proposed Trade:** {thesis.proposed_trade}  ",
            f"**Direction:** {thesis.direction if hasattr(thesis, 'direction') else 'N/A'}  ",
            f"",
        ]

    # Evidence FOR
    if report.evidence_for:
        lines += [
            f"## Evidence Supporting the Thesis ({len(report.evidence_for)} items)",
            f"",
        ]
        for item in report.evidence_for:
            lines += [
                f"**{item.data_point}**  ",
                f"*Source: {item.citation}*  ",
                f"Confidence: {item.confidence * 100:.0f}%  ",
                f"{item.reasoning}",
                f"",
            ]

    # Evidence AGAINST
    if report.evidence_against:
        lines += [
            f"## Evidence Against the Thesis ({len(report.evidence_against)} items)",
            f"",
        ]
        for item in report.evidence_against:
            lines += [
                f"**{item.data_point}**  ",
                f"*Source: {item.citation}*  ",
                f"Confidence: {item.confidence * 100:.0f}%  ",
                f"{item.reasoning}",
                f"",
            ]

    # Evidence NEUTRAL
    if report.evidence_neutral:
        lines += [
            f"## Informational Evidence ({len(report.evidence_neutral)} items)",
            f"",
        ]
        for item in report.evidence_neutral:
            lines += [
                f"- **{item.data_point}** ({item.citation}): {item.reasoning}",
            ]
        lines.append("")

    # Risk Assessment
    lines += [
        f"## Risk Assessment",
        f"",
        f"**Overall Risk Score:** {risk.risk_score}  ",
    ]
    if risk.max_loss_scenario:
        lines.append(f"**Worst-Case Scenario:** {risk.max_loss_scenario}  ")
    if risk.var_estimate:
        lines.append(f"**VaR Estimate:** {risk.var_estimate}  ")
    if risk.portfolio_impact:
        lines.append(f"**Portfolio Impact:** {risk.portfolio_impact}  ")
    if risk.greeks_summary:
        lines.append(f"**Greeks:** {risk.greeks_summary}  ")
    if risk.concentration_risk:
        lines.append(f"**Concentration:** {risk.concentration_risk}  ")
    lines.append("")

    # Refinements
    if report.refinements:
        lines += [
            f"## Suggested Refinements",
            f"",
        ]
        for ref in report.refinements:
            lines.append(f"- {ref}")
        lines.append("")

    # Footer
    lines += [
        f"---",
        f"",
        f"*Validated using {report.tool_calls_made} MCP tool calls "
        f"({report.tool_calls_succeeded} succeeded) in {report.total_latency_ms:.0f}ms.*  ",
        f"* — Thesis Validation Pipeline v1.0*",
    ]

    return "\n".join(lines)
