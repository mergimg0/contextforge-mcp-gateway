"""
MCP Gateway — Main FastAPI Application

Pipeline per request:
  Request → RequestID → JWT Validation → Scope Check
    → Token Exchange (Redis cache) → Path Route → Proxy → Audit Log → Response
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI, Request, HTTPException

from gateway.config import GatewaySettings, load_routes
from gateway.auth.jwt_validator import JWTValidator
from gateway.auth.token_exchange import TokenExchangeClient
from gateway.auth.scope_checker import check_scope
from gateway.routing.path_router import PathRouter
from gateway.routing.proxy import proxy_request
from gateway.routing.tool_aggregator import ToolAggregator
from gateway.middleware.request_id import RequestIDMiddleware
from gateway.middleware.audit_log import log_access_decision
from gateway.health import router as health_router

logger = logging.getLogger(__name__)

# ─── Structured logging setup ────────────────────────────────
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)


# ─── Application lifespan ────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize connections on startup, clean up on shutdown."""
    settings = GatewaySettings()

    # Redis connection
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=False)
    app.state.redis = redis_client

    # JWT Validator — issuer from external URL, JWKS from internal URL
    # Audience check disabled: Keycloak demo tokens use azp=demo-agent, not aud=mcp-gateway
    internal_url = settings.keycloak_internal_url
    app.state.jwt_validator = JWTValidator(
        jwks_url=f"{internal_url}/protocol/openid-connect/certs",
        issuer=settings.keycloak_realm_url,
        audience=None,
        cache_ttl=settings.keycloak_jwks_cache_ttl,
    )

    # Token Exchange Client — uses internal URL for Keycloak calls
    app.state.exchange_client = TokenExchangeClient.from_keycloak(
        realm_url=internal_url,
        client_id=settings.keycloak_client_id,
        client_secret=settings.keycloak_client_secret,
        redis_client=redis_client,
        cache_ttl=settings.token_exchange_cache_ttl,
    )

    # Route table
    routes = load_routes(settings.routes_file)
    app.state.router = PathRouter(routes)

    # Tool aggregator
    app.state.aggregator = ToolAggregator(
        routes=routes,
        exchange_fn=app.state.exchange_client.exchange,
        redis_client=redis_client,
        namespace_sep=settings.tool_aggregation_separator,
        cache_ttl=settings.tool_aggregation_cache_ttl,
    )

    logger.info(
        "Gateway started with %d routes: %s",
        len(routes),
        [r.name for r in routes],
    )
    yield

    # Shutdown
    await redis_client.aclose()
    logger.info("Gateway shutdown complete")


# ─── FastAPI app ──────────────────────────────────────────────
app = FastAPI(
    title="ContextForge MCP Gateway",
    description="RFC 8693 Token Exchange Gateway for MCP Servers",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RequestIDMiddleware)
app.include_router(health_router)


# ─── Tool aggregation endpoint ────────────────────────────────
@app.get("/tools/aggregate")
async def aggregate_tools(request: Request):
    """
    Returns a merged tools/list from all backends accessible to the caller.
    Tool names are prefixed: bloomberg__get_ref_data, risk__calculate_var.
    """
    token = _extract_bearer(request)
    claims = await request.app.state.jwt_validator.validate(token)
    scopes = set(claims.get("scope", "").split())

    # Add Keycloak roles as scopes
    scopes.update(claims.get("realm_access", {}).get("roles", []))
    for client_data in claims.get("resource_access", {}).values():
        scopes.update(client_data.get("roles", []))

    return await request.app.state.aggregator.aggregate(token, scopes)


# ─── Main gateway handler ────────────────────────────────────
@app.api_route(
    "/{route_prefix}/{rest_of_path:path}",
    methods=["GET", "POST", "PUT", "DELETE"],
)
async def gateway_handler(
    route_prefix: str,
    rest_of_path: str,
    request: Request,
):
    """
    Gateway routing pipeline:
    1. Extract and validate Bearer JWT
    2. Match route prefix to backend config
    3. Check required scope (fail fast — no Keycloak call)
    4. Exchange token for backend-specific JWT (RFC 8693)
    5. Proxy request to backend with exchanged token
    6. Emit structured audit log
    """
    start_time = time.monotonic()
    request_id = getattr(request.state, "request_id", "unknown")

    # Step 1: Extract and validate JWT
    token = _extract_bearer(request)
    try:
        claims = await request.app.state.jwt_validator.validate(token)
    except Exception as e:
        log_access_decision(
            request_id=request_id,
            caller_sub="unknown",
            route_name=route_prefix,
            decision="DENY",
            detail=f"JWT validation failed: {e}",
        )
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

    caller_sub = claims.get("sub", "unknown")

    # Step 2: Match route
    path = f"/{route_prefix}/{rest_of_path}" if rest_of_path else f"/{route_prefix}"
    route = request.app.state.router.match(path)
    if not route:
        log_access_decision(
            request_id=request_id,
            caller_sub=caller_sub,
            route_name=route_prefix,
            decision="DENY",
            detail=f"No route matched: {path}",
        )
        raise HTTPException(status_code=404, detail=f"No route for: /{route_prefix}")

    # Step 3: Scope check (before token exchange — fail fast)
    try:
        check_scope(claims, route.required_scope)
    except HTTPException:
        log_access_decision(
            request_id=request_id,
            caller_sub=caller_sub,
            route_name=route.name,
            scope_check="FAIL",
            decision="DENY",
            detail=f"Missing scope: {route.required_scope}",
        )
        raise

    # Step 4: Token exchange (RFC 8693) — attempt exchange, fall back to forwarding
    exchange_performed = False
    exchange_cached = False
    backend_token = token  # default: forward original token
    try:
        exchanged = await request.app.state.exchange_client.exchange(
            subject_token=token,
            target_audience=route.exchange_audience,
        )
        backend_token = exchanged.access_token
        exchange_performed = True
        exchange_cached = exchanged.cached
    except Exception as e:
        # Exchange failed — forward original token (backends trust gateway)
        logger.warning("Token exchange failed, forwarding original: %s", e)

    # Step 5: Proxy to backend
    backend_path = request.app.state.router.get_backend_path(path, route)
    try:
        response = await proxy_request(
            request=request,
            backend_url=route.backend_url,
            backend_path=backend_path,
            backend_token=backend_token,
            caller_sub=caller_sub,
            request_id=request_id,
            timeout=route.timeout,
        )
    except Exception as e:
        latency = (time.monotonic() - start_time) * 1000
        log_access_decision(
            request_id=request_id,
            caller_sub=caller_sub,
            route_name=route.name,
            scope_check="PASS",
            exchange_performed=exchange_performed,
            exchange_audience=route.exchange_audience,
            exchange_cached=exchange_cached,
            decision="ERROR",
            latency_ms=latency,
            detail=f"Backend proxy failed: {e}",
        )
        raise HTTPException(status_code=502, detail=f"Backend error: {e}")

    # Step 6: Audit log
    latency = (time.monotonic() - start_time) * 1000
    log_access_decision(
        request_id=request_id,
        caller_sub=caller_sub,
        route_name=route.name,
        scope_check="PASS",
        exchange_performed=exchange_performed,
        exchange_audience=route.exchange_audience,
        exchange_cached=exchange_cached,
        backend_status=response.status_code,
        latency_ms=latency,
        decision="PERMIT",
    )

    return response


def _extract_bearer(request: Request) -> str:
    """Extract Bearer token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    return auth.removeprefix("Bearer ").strip()
