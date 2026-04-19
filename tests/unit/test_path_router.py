"""Unit tests for path-based routing."""

from __future__ import annotations

from gateway.config import RouteConfig
from gateway.routing.path_router import PathRouter


def _make_routes() -> list[RouteConfig]:
    return [
        RouteConfig(
            name="bloomberg", path_prefix="/bloomberg",
            backend_url="http://bloomberg:8010/mcp",
            required_scope="bloomberg:read", exchange_audience="bloomberg-mcp",
        ),
        RouteConfig(
            name="risk", path_prefix="/risk",
            backend_url="http://risk:8011/mcp",
            required_scope="risk:read", exchange_audience="risk-mcp",
        ),
        RouteConfig(
            name="research", path_prefix="/research",
            backend_url="http://research:8012/mcp",
            required_scope="research:read", exchange_audience="research-mcp",
        ),
    ]


class TestPathRouter:
    def test_exact_match(self):
        router = PathRouter(_make_routes())
        route = router.match("/bloomberg")
        assert route is not None
        assert route.name == "bloomberg"

    def test_prefix_match(self):
        router = PathRouter(_make_routes())
        route = router.match("/bloomberg/mcp")
        assert route is not None
        assert route.name == "bloomberg"

    def test_deep_path_match(self):
        router = PathRouter(_make_routes())
        route = router.match("/risk/mcp/extra/path")
        assert route is not None
        assert route.name == "risk"

    def test_no_match(self):
        router = PathRouter(_make_routes())
        route = router.match("/nonexistent")
        assert route is None

    def test_backend_path_extraction(self):
        router = PathRouter(_make_routes())
        route = router.match("/bloomberg/mcp")
        assert route is not None
        path = router.get_backend_path("/bloomberg/mcp", route)
        assert path == "/mcp"

    def test_backend_path_root(self):
        router = PathRouter(_make_routes())
        route = router.match("/bloomberg")
        assert route is not None
        path = router.get_backend_path("/bloomberg", route)
        assert path == "/"

    def test_all_routes_accessible(self):
        router = PathRouter(_make_routes())
        assert len(router.routes) == 3
        names = {r.name for r in router.routes}
        assert names == {"bloomberg", "risk", "research"}
