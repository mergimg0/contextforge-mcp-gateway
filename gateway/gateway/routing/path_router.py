"""Path-based routing: match request path prefix to backend MCP server."""

from __future__ import annotations

from typing import Optional

from gateway.config import RouteConfig


class PathRouter:
    """
    Longest-prefix match router for MCP gateway routes.

    Routes are registered from config/routes.yaml. Each route maps
    a path prefix (e.g. '/bloomberg') to a backend URL, required scope,
    and token exchange audience.
    """

    def __init__(self, routes: list[RouteConfig]) -> None:
        # Sort by prefix length descending for longest-match semantics
        self._routes = sorted(routes, key=lambda r: len(r.path_prefix), reverse=True)
        self._route_map = {r.path_prefix.strip("/"): r for r in routes}

    def match(self, path: str) -> Optional[RouteConfig]:
        """
        Find the route matching the given request path.

        Uses longest-prefix match: /bloomberg/extra matches /bloomberg.
        Returns None if no route matches.
        """
        # Normalise: strip leading slash, get first segment
        clean = path.strip("/")
        for route in self._routes:
            prefix = route.path_prefix.strip("/")
            if clean == prefix or clean.startswith(prefix + "/"):
                return route
        return None

    def get_backend_path(self, path: str, route: RouteConfig) -> str:
        """
        Extract the path portion after the route prefix.

        /bloomberg/mcp → /mcp (forwarded to backend)
        /bloomberg → / (root)
        """
        prefix = route.path_prefix.strip("/")
        clean = path.strip("/")
        remainder = clean[len(prefix):]
        if not remainder:
            return "/"
        return remainder if remainder.startswith("/") else f"/{remainder}"

    @property
    def routes(self) -> list[RouteConfig]:
        return list(self._routes)
