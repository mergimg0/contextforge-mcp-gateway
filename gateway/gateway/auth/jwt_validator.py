"""JWT validation against Keycloak JWKS with caching and key rotation handling."""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field

import httpx
import jwt
from jwt import PyJWKClient, PyJWK

logger = logging.getLogger(__name__)


@dataclass
class JWKSCache:
    """Cached JWKS keys with TTL-based expiry."""

    keys: list[PyJWK] = field(default_factory=list)
    fetched_at: float = 0.0
    ttl: int = 3600

    @property
    def is_expired(self) -> bool:
        return time.time() - self.fetched_at > self.ttl


class JWTValidator:
    """
    Validates Bearer JWTs against Keycloak's JWKS endpoint.

    Features:
    - JWKS caching with configurable TTL
    - Automatic key rotation handling (re-fetch on signature failure)
    - Validates: signature, issuer, audience, expiry, not-before
    """

    def __init__(
        self,
        jwks_url: str,
        issuer: str,
        audience: str,
        cache_ttl: int = 3600,
    ) -> None:
        self.jwks_url = jwks_url
        self.issuer = issuer
        self.audience = audience
        self._jwk_client = PyJWKClient(jwks_url, cache_keys=True, lifespan=cache_ttl)
        self._cache = JWKSCache(ttl=cache_ttl)

    async def validate(self, token: str) -> dict:
        """
        Validate a Bearer JWT and return its claims.

        Raises jwt.InvalidTokenError on any validation failure.
        On signature failure, re-fetches JWKS once to handle key rotation.
        """
        try:
            return self._decode(token)
        except jwt.InvalidSignatureError:
            logger.info("JWT signature failed — re-fetching JWKS for key rotation")
            self._jwk_client = PyJWKClient(
                self.jwks_url, cache_keys=True, lifespan=self._cache.ttl
            )
            return self._decode(token)

    def _decode(self, token: str) -> dict:
        """Decode and validate JWT using cached JWKS."""
        signing_key = self._jwk_client.get_signing_key_from_jwt(token)
        options = {
            "verify_exp": True,
            "verify_nbf": True,
            "verify_iss": True,
            "verify_aud": self.audience is not None,
        }
        kwargs: dict = {
            "algorithms": ["RS256"],
            "issuer": self.issuer,
            "options": options,
        }
        if self.audience:
            kwargs["audience"] = self.audience
        return jwt.decode(token, signing_key.key, **kwargs)

    @classmethod
    def from_keycloak(
        cls,
        realm_url: str,
        audience: str = "mcp-gateway",
        cache_ttl: int = 3600,
    ) -> "JWTValidator":
        """Create a validator configured for a Keycloak realm."""
        return cls(
            jwks_url=f"{realm_url}/protocol/openid-connect/certs",
            issuer=realm_url,
            audience=audience,
            cache_ttl=cache_ttl,
        )
