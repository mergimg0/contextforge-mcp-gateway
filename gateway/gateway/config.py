"""Gateway configuration loaded from environment and routes.yaml."""

from __future__ import annotations

import yaml
from pathlib import Path
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class KeycloakConfig(BaseModel):
    realm_url: str = "http://keycloak:8080/realms/trading"
    client_id: str = "mcp-gateway"
    client_secret: str = ""
    jwks_cache_ttl: int = 3600


class TokenExchangeConfig(BaseModel):
    enabled: bool = True
    cache_ttl: int = 300
    cache_prefix: str = "te:"


class RouteConfig(BaseModel):
    name: str
    path_prefix: str
    backend_url: str
    required_scope: str
    exchange_audience: str
    timeout: int = 30


class ToolAggregationConfig(BaseModel):
    enabled: bool = True
    namespace_separator: str = "__"
    cache_ttl: int = 60


class GatewaySettings(BaseSettings):
    """Top-level settings loaded from environment variables."""

    keycloak_realm_url: str = "http://localhost:8080/realms/trading"
    keycloak_internal_url: str = "http://keycloak:8080/realms/trading"
    keycloak_client_id: str = "mcp-gateway"
    keycloak_client_secret: str = ""
    keycloak_jwks_cache_ttl: int = 3600

    redis_url: str = "redis://redis:6379/0"

    routes_file: str = "/app/config/routes.yaml"

    token_exchange_enabled: bool = True
    token_exchange_cache_ttl: int = 300

    tool_aggregation_enabled: bool = True
    tool_aggregation_separator: str = "__"
    tool_aggregation_cache_ttl: int = 60

    log_level: str = "INFO"

    model_config = {"env_prefix": "GATEWAY_"}


def load_routes(path: str) -> list[RouteConfig]:
    """Load route definitions from YAML config file."""
    config_path = Path(path)
    if not config_path.exists():
        return []
    with open(config_path) as f:
        data = yaml.safe_load(f)
    raw_routes = data.get("gateway", {}).get("routes", [])
    return [RouteConfig(**r) for r in raw_routes]
