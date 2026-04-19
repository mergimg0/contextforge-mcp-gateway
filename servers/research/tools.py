"""
Research MCP tool implementations.

These tools provide access to ContextForge's internal research document library.
They are cross-desk accessible (no desk isolation enforcement) but use the
caller's desk context to optionally bias search relevance.

NOTE: These tools are NOT for real-time market data — use bloomberg tools
for live quotes, reference data, and real-time analytics.  Use risk tools
for portfolio-level VaR, scenario analysis, and Greeks aggregation.
"""

from __future__ import annotations

import math
import re
from typing import Optional

import structlog
from mcp.server.fastmcp import Context

from .documents import get_document_by_id, keyword_search

audit_log = structlog.get_logger("mcp.audit")
logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _caller_context(ctx: Context) -> tuple[str, list[str]]:
    """Extract subject and desk_access from JWT claims without enforcement."""
    claims = ctx.auth or {}
    subject = claims.get("sub", "unknown")
    desk_access = claims.get("desk_access", [])
    if isinstance(desk_access, str):
        desk_access = [desk_access]
    return subject, desk_access


def _extractive_summary(content: str, max_length: int) -> str:
    """
    Simple extractive summarization: score sentences by position and
    term frequency, return top sentences up to max_length characters.
    """
    sentences = re.split(r"(?<=[.!?])\s+", content.strip())
    if not sentences:
        return content[:max_length]

    # Score by position (first > last > middle) and length (prefer medium-length)
    scored: list[tuple[float, int, str]] = []
    n = len(sentences)
    for i, sent in enumerate(sentences):
        position_score = 1.0 if i == 0 else (0.6 if i == n - 1 else 0.3)
        length_score = min(len(sent), 120) / 120.0
        score = position_score + 0.4 * length_score
        scored.append((score, i, sent))

    scored.sort(key=lambda x: x[0], reverse=True)

    selected: list[tuple[int, str]] = []
    total_len = 0
    for _, idx, sent in scored:
        if total_len + len(sent) + 1 > max_length:
            break
        selected.append((idx, sent))
        total_len += len(sent) + 1

    # Re-order by original position for coherence
    selected.sort(key=lambda x: x[0])
    return " ".join(s for _, s in selected)


def _extract_key_findings(content: str, n: int = 3) -> list[str]:
    """
    Heuristic extraction of key findings: sentences that start with
    phrases like 'Key finding', 'Recommendation', or contain numbers.
    """
    sentences = re.split(r"(?<=[.!?])\s+", content.strip())
    finding_patterns = re.compile(
        r"(key finding|recommendation|result|finding|signal|implication|"
        r"trade recommendation|position recommendation|\bshows?\b|\bsuggests?\b|"
        r"\d+\.\d+|\d+%)",
        re.IGNORECASE,
    )
    findings = [s.strip() for s in sentences if finding_patterns.search(s)]
    if not findings:
        # Fall back to first n sentences
        findings = [s.strip() for s in sentences[:n]]
    return findings[:n]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def search_research(
    query: str,
    ctx: Context,
    max_results: int = 5,
    desk: Optional[str] = None,
) -> dict:
    """
    Search ContextForge's internal research document library using keyword/TF-IDF
    matching.

    NOT for real-time market data — use bloomberg tools for live quotes,
    time-series data, and reference data lookups.

    Research covers: volatility surface analysis, IV-RV spread studies,
    earnings vol research, sector dispersion, macro vol regime reports,
    Greek sensitivity studies, options flow analysis, and correlation research.

    Parameters
    ----------
    query:
        Free-text search query. Supports natural language or keyword search.
        Examples: "vol surface skew richness", "earnings implied move",
        "correlation breakdown stress event"
    max_results:
        Maximum number of results to return (1–20). Default 5.
    desk:
        Optional desk hint for relevance filtering. When provided, documents
        tagged for that desk are preferred. Does NOT restrict access — research
        is cross-desk accessible. Valid values: equities, rates, vol, macro, credit.
    ctx:
        MCP request context (injected automatically; do not pass explicitly).

    Returns
    -------
    dict with keys:
        query: the original query string
        results: list of {doc_id, title, relevance_score, snippet, author, date, tags}
        total_found: number of results returned
        desk_filter_applied: whether desk filtering was applied
    """
    subject, desk_access = _caller_context(ctx)

    # Clamp max_results
    max_results = max(1, min(max_results, 20))

    # Determine desk filter — use caller's primary desk if not explicitly provided
    desk_filter: Optional[list[str]] = None
    desk_filter_applied = False
    if desk:
        desk_filter = [desk]
        desk_filter_applied = True
    # NOTE: We do NOT enforce desk isolation for research — cross-desk access is intentional.
    # The desk parameter is an optional relevance hint, not an access control mechanism.

    results = keyword_search(query, max_results=max_results, desk_filter=desk_filter)

    # If desk filter returned fewer results than requested, supplement with global search
    if desk_filter and len(results) < max_results:
        global_results = keyword_search(query, max_results=max_results)
        seen_ids = {r["doc_id"] for r in results}
        for r in global_results:
            if r["doc_id"] not in seen_ids and len(results) < max_results:
                results.append(r)
                seen_ids.add(r["doc_id"])

    audit_log.info(
        "research_search",
        subject=subject,
        desk_access=desk_access,
        query=query[:120],
        desk_hint=desk,
        results_returned=len(results),
    )

    return {
        "query": query,
        "results": results,
        "total_found": len(results),
        "desk_filter_applied": desk_filter_applied,
    }


async def get_document(doc_id: str, ctx: Context) -> dict:
    """
    Retrieve a full research document by its ID.

    NOT for real-time market data — use bloomberg tools for live prices,
    curves, and analytics. NOT for position or risk data — use risk tools.

    Use search_research first to discover relevant document IDs, then call
    this tool to retrieve the full document content including citations.

    Parameters
    ----------
    doc_id:
        Document identifier (e.g. "VOL-2025-001", "EQ-2025-003").
        Obtain IDs from search_research results.
    ctx:
        MCP request context (injected automatically; do not pass explicitly).

    Returns
    -------
    dict with keys:
        doc_id, title, content, author, date, tags, citations, desk_relevance
        OR error: "not_found" if the document ID does not exist.
    """
    from mcp import McpError
    from mcp.types import ErrorCode

    subject, desk_access = _caller_context(ctx)

    doc = get_document_by_id(doc_id)
    if doc is None:
        audit_log.warning(
            "research_get_document_not_found",
            subject=subject,
            doc_id=doc_id,
        )
        raise McpError(
            ErrorCode.INVALID_PARAMS,
            f"Document '{doc_id}' not found. Use search_research to discover valid IDs.",
        )

    audit_log.info(
        "research_get_document",
        subject=subject,
        desk_access=desk_access,
        doc_id=doc_id,
        title=doc["title"],
    )

    return {
        "doc_id": doc["id"],
        "title": doc["title"],
        "content": doc["content"],
        "author": doc["author"],
        "date": doc["date"],
        "tags": doc["tags"],
        "citations": doc["citations"],
        "desk_relevance": doc["desk_relevance"],
    }


async def summarize(doc_id: str, ctx: Context, max_length: int = 200) -> dict:
    """
    Generate a concise extractive summary of a research document.

    NOT a substitute for reading the full document when precise data points
    or trade recommendations are needed. NOT for real-time data — use
    bloomberg tools for current prices and analytics.

    Produces a short summary by extracting the most informative sentences
    from the document, along with a list of key findings.

    Parameters
    ----------
    doc_id:
        Document identifier (e.g. "VOL-2025-001"). Use search_research to
        find relevant document IDs before calling this tool.
    max_length:
        Target maximum character length of the summary (50–1000). Default 200.
        The summary may be slightly shorter to avoid cutting mid-sentence.
    ctx:
        MCP request context (injected automatically; do not pass explicitly).

    Returns
    -------
    dict with keys:
        doc_id: document identifier
        title: document title
        summary: extractive summary up to max_length characters
        key_findings: list of up to 3 key finding sentences from the document
        author: document author
        date: publication date
    """
    from mcp import McpError
    from mcp.types import ErrorCode

    subject, desk_access = _caller_context(ctx)

    doc = get_document_by_id(doc_id)
    if doc is None:
        audit_log.warning(
            "research_summarize_not_found",
            subject=subject,
            doc_id=doc_id,
        )
        raise McpError(
            ErrorCode.INVALID_PARAMS,
            f"Document '{doc_id}' not found. Use search_research to discover valid IDs.",
        )

    max_length = max(50, min(max_length, 1000))

    summary = _extractive_summary(doc["content"], max_length=max_length)
    key_findings = _extract_key_findings(doc["content"], n=3)

    audit_log.info(
        "research_summarize",
        subject=subject,
        desk_access=desk_access,
        doc_id=doc_id,
        max_length=max_length,
    )

    return {
        "doc_id": doc["id"],
        "title": doc["title"],
        "summary": summary,
        "key_findings": key_findings,
        "author": doc["author"],
        "date": doc["date"],
    }
