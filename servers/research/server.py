"""
Research MCP backend server.

Provides cross-desk access to internal research documents covering:
  - Volatility surface analysis and skew dynamics
  - IV-RV spread studies and variance swap analytics
  - Earnings volatility research
  - Sector dispersion analysis
  - Macro volatility regime reports
  - Greek sensitivity studies (vanna, volga, GEX)
  - Options flow analysis
  - Correlation and tail risk research

Transport:  streamable-http
Host:       0.0.0.0
Port:       8012
Path:       /mcp

Authentication: Bearer JWT validated against Keycloak realm "trading".
Audience:  research-mcp
Scope:     research:read

Research is cross-desk accessible — desk context is used as an optional
relevance hint for search, not as an access control boundary.

NOT for real-time market data (use bloomberg tools) or portfolio risk
calculations (use risk tools).
"""

from __future__ import annotations

import sys
import os

# Allow the shared package to be imported when running inside the container
# (PYTHONPATH is set in the Dockerfile, but support running locally too)
_here = os.path.dirname(__file__)
_servers_root = os.path.dirname(_here)
if _servers_root not in sys.path:
    sys.path.insert(0, _servers_root)

import structlog
from mcp.server.fastmcp import FastMCP

from .tools import get_document, search_research, summarize

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# FastMCP server — gateway handles auth, backend trusts gateway
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="contextforge-research",
    instructions=(
        " — Research Library MCP Server.\n\n"
        "Provides semantic search and retrieval over internal research documents. "
        "Research is cross-desk accessible; the optional 'desk' parameter biases "
        "relevance toward desk-specific documents but does not restrict access.\n\n"
        "Available tools:\n"
        "  search_research  — keyword/TF-IDF search over all research documents\n"
        "  get_document     — retrieve full document by ID\n"
        "  summarize        — extractive summary and key findings for a document\n\n"
        "NOT for real-time market data (use bloomberg tools) or risk calculations "
        "(use risk tools)."
    ),
)

# ---------------------------------------------------------------------------
# Register tools
# ---------------------------------------------------------------------------

mcp.tool()(search_research)
mcp.tool()(get_document)
mcp.tool()(summarize)

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    os.environ.setdefault("MCP_HTTP_HOST", "0.0.0.0")
    os.environ.setdefault("MCP_HTTP_PORT", "8012")
    logger.info("research_mcp_starting", port=8012)
    mcp.run(transport="streamable-http")
