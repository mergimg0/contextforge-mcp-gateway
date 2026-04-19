"""Shared auth utilities for MCP backend servers.

In the gateway architecture, authentication and token exchange happen
at the gateway layer. Backend MCP servers trust the gateway and read
caller identity from the X-Caller-Sub header propagated by the gateway.

For production, each backend would also validate the exchanged JWT.
For this demo, we trust the gateway's forwarded identity.
"""

from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)


def get_caller_from_context(ctx) -> dict:
    """
    Extract caller identity from MCP context.

    In the gateway architecture:
    - The gateway validates the original JWT
    - The gateway performs RFC 8693 token exchange
    - The gateway forwards X-Caller-Sub header to backends
    - Backends read caller identity from ctx or headers

    Returns a dict with sub, desk_access, and actor fields.
    """
    # Try to get auth from MCP context (if auth is configured)
    if hasattr(ctx, 'auth') and ctx.auth:
        return ctx.auth

    # Fallback: return a minimal context for demo mode
    return {
        "sub": "demo-user",
        "desk_access": ["equities", "rates", "vol", "macro", "credit"],
    }
