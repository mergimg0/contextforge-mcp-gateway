"""Merge tools/list from all accessible backend MCP servers."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

import httpx
import redis.asyncio as aioredis

from gateway.config import RouteConfig

logger = logging.getLogger(__name__)


class ToolAggregator:
    """
    Fetches tools/list from all backend MCP servers accessible to the caller,
    merges them into a single manifest with namespaced tool names.

    bloomberg__get_ref_data, risk__calculate_var, research__search_research

    Caches the merged manifest in Redis per caller scope set.
    """

    def __init__(
        self,
        routes: list[RouteConfig],
        exchange_fn,
        redis_client: Optional[aioredis.Redis] = None,
        namespace_sep: str = "__",
        cache_ttl: int = 60,
    ) -> None:
        self.routes = routes
        self.exchange_fn = exchange_fn
        self.redis = redis_client
        self.sep = namespace_sep
        self.cache_ttl = cache_ttl

    async def aggregate(
        self,
        subject_token: str,
        caller_scopes: set[str],
    ) -> dict:
        """
        Fetch and merge tools from all backends the caller can access.

        Filters routes by caller scopes, exchanges tokens per backend,
        fetches tools/list, and namespaces tool names.
        """
        # Filter to routes the caller has scope for
        accessible = [r for r in self.routes if r.required_scope in caller_scopes]

        if not accessible:
            return {"tools": [], "count": 0}

        # Check cache
        cache_key = self._cache_key(caller_scopes)
        if self.redis:
            cached = await self.redis.get(cache_key)
            if cached:
                return json.loads(cached)

        # Fetch from all accessible backends in parallel
        tasks = [
            self._fetch_tools(route, subject_token)
            for route in accessible
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_tools = []
        for route, result in zip(accessible, results):
            if isinstance(result, BaseException):
                logger.warning(
                    "Failed to fetch tools from %s: %s", route.name, result
                )
                continue
            tools: list[dict] = result
            prefix = route.name
            for tool in tools:
                tool["name"] = f"{prefix}{self.sep}{tool['name']}"
            all_tools.extend(tools)

        response = {"tools": all_tools, "count": len(all_tools)}

        # Cache
        if self.redis:
            await self.redis.setex(
                cache_key, self.cache_ttl, json.dumps(response)
            )

        return response

    async def _fetch_tools(
        self,
        route: RouteConfig,
        subject_token: str,
    ) -> list[dict]:
        """Fetch tools/list from a single backend MCP server."""
        exchanged = await self.exchange_fn(subject_token, route.exchange_audience)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                route.backend_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {},
                },
                headers={"Authorization": f"Bearer {exchanged.access_token}"},
            )

        if resp.status_code != 200:
            raise RuntimeError(f"Backend {route.name} returned {resp.status_code}")

        data = resp.json()
        return data.get("result", {}).get("tools", [])

    def _cache_key(self, scopes: set[str]) -> str:
        scope_str = ",".join(sorted(scopes))
        return f"agg:tools:{scope_str}"
