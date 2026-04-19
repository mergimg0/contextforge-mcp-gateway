"""
Pydantic models for the synthesiser layer.
"""

from typing import Optional

from pydantic import BaseModel, Field


class EvidenceClassification(str):
    FOR = "FOR"
    AGAINST = "AGAINST"
    NEUTRAL = "NEUTRAL"


class RiskScore(str):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


class EvidenceItem(BaseModel):
    """
    A single piece of evidence extracted from a tool call result.

    Evidence is classified as FOR (supports the thesis), AGAINST (contradicts
    it), or NEUTRAL (informational but not directionally conclusive).
    """

    source: str = Field(description="Server and tool that produced this evidence (e.g. 'bloomberg/get_history')")
    data_point: str = Field(description="The specific data point or metric (e.g. 'IV-RV spread: 8.2 vols')")
    classification: str = Field(description="FOR | AGAINST | NEUTRAL")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in this evidence item (0–1)")
    citation: str = Field(description="Short citation linking data_point to its source")
    reasoning: str = Field(description="One to two sentence analyst-style reasoning for the classification")


class RiskAssessment(BaseModel):
    """Portfolio risk dimensions extracted from risk tool results."""

    max_loss_scenario: Optional[str] = Field(
        default=None,
        description="Description of worst-case scenario and estimated P&L impact",
    )
    portfolio_impact: Optional[str] = Field(
        default=None,
        description="Estimated portfolio-level P&L impact of the proposed trade",
    )
    concentration_risk: Optional[str] = Field(
        default=None,
        description="Whether the trade creates unacceptable concentration in a risk factor",
    )
    var_estimate: Optional[str] = Field(
        default=None,
        description="VaR estimate from the risk tools if available",
    )
    greeks_summary: Optional[str] = Field(
        default=None,
        description="Summary of key Greeks exposures if option-related",
    )
    risk_score: str = Field(
        default="MEDIUM",
        description="Overall risk rating: LOW | MEDIUM | HIGH | EXTREME",
    )


class ValidationReport(BaseModel):
    """
    The final output of the thesis validation pipeline.

    Contains structured evidence, risk assessment, overall verdict,
    and suggested refinements for the PM.
    """

    thesis_raw: str = Field(description="Original thesis text")
    asset: str = Field(description="Primary asset identified")
    claim_type: str = Field(description="Claim type identified by parser")

    verdict: str = Field(description="SUPPORTED | UNSUPPORTED | INCONCLUSIVE")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall confidence score (0–1), weighted average of evidence confidences",
    )

    evidence_for: list[EvidenceItem] = Field(
        default_factory=list,
        description="Evidence items that support the thesis",
    )
    evidence_against: list[EvidenceItem] = Field(
        default_factory=list,
        description="Evidence items that contradict the thesis",
    )
    evidence_neutral: list[EvidenceItem] = Field(
        default_factory=list,
        description="Informational evidence with no directional implication",
    )

    risk_assessment: RiskAssessment = Field(
        description="Risk dimensions extracted from risk tool results",
    )

    refinements: list[str] = Field(
        default_factory=list,
        description="Suggested thesis refinements or additional data to gather",
    )

    tool_calls_made: int = Field(description="Total number of MCP tool calls executed")
    tool_calls_succeeded: int = Field(description="Number of tool calls that succeeded")
    total_latency_ms: float = Field(description="Total wall-clock latency of the pipeline (ms)")

    markdown_summary: str = Field(
        default="",
        description="Full analyst-style markdown report",
    )
