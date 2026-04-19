"""RFC 8693 Token Exchange client with Redis caching."""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx
import jwt
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


@dataclass
class ExchangedToken:
    """Result of a successful RFC 8693 token exchange."""

    access_token: str
    audience: str
    subject: str
    actor: str
    expires_at: float
    cached: bool = False


class TokenExchangeClient:
    """
    RFC 8693 Token Exchange via Keycloak 26.2+.

    Exchanges a broad gateway-audience token for a narrowed
    backend-specific token. Caches exchanged tokens in Redis
    to avoid redundant Keycloak round-trips.

    Cache key: sha256(subject_token_jti + target_audience)
    Cache TTL: min(token_exp - now, configured max TTL)
    """

    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        redis_client: Optional[aioredis.Redis] = None,
        cache_ttl: int = 300,
        cache_prefix: str = "te:",
    ) -> None:
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.redis = redis_client
        self.cache_ttl = cache_ttl
        self.cache_prefix = cache_prefix

    async def exchange(
        self,
        subject_token: str,
        target_audience: str,
    ) -> ExchangedToken:
        """
        Exchange a gateway JWT for a backend-specific JWT via RFC 8693.

        Checks Redis cache first. On cache miss, calls Keycloak and caches result.
        """
        cache_key = self._cache_key(subject_token, target_audience)

        # Check cache
        if self.redis:
            cached = await self.redis.get(cache_key)
            if cached:
                cached_token = cached.decode("utf-8")
                claims = jwt.decode(cached_token, options={"verify_signature": False})
                logger.debug("Token exchange cache HIT for audience=%s", target_audience)
                return ExchangedToken(
                    access_token=cached_token,
                    audience=target_audience,
                    subject=claims.get("sub", "unknown"),
                    actor=claims.get("act", {}).get("sub", "unknown"),
                    expires_at=claims.get("exp", 0),
                    cached=True,
                )

        # Cache miss — call Keycloak
        logger.info("Token exchange cache MISS — calling Keycloak for audience=%s", target_audience)
        exchanged = await self._call_keycloak(subject_token, target_audience)

        # Cache the result
        if self.redis:
            ttl = min(int(exchanged.expires_at - time.time()), self.cache_ttl)
            if ttl > 0:
                await self.redis.setex(cache_key, ttl, exchanged.access_token)

        return exchanged

    async def _call_keycloak(
        self,
        subject_token: str,
        target_audience: str,
    ) -> ExchangedToken:
        """Execute the RFC 8693 token exchange request against Keycloak."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                self.token_url,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                    "subject_token": subject_token,
                    "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
                    "audience": target_audience,
                    "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if resp.status_code == 400:
            error_data = resp.json()
            error_type = error_data.get("error", "unknown")
            error_desc = error_data.get("error_description", "")
            if error_type == "invalid_client":
                raise PermissionError(
                    f"Gateway not authorized to exchange for audience '{target_audience}'. "
                    f"Check Keycloak token exchange policy. Detail: {error_desc}"
                )
            raise ValueError(f"Token exchange rejected: {error_type} — {error_desc}")

        if resp.status_code != 200:
            raise RuntimeError(
                f"Keycloak exchange failed [{resp.status_code}]: {resp.text}"
            )

        token_data = resp.json()
        new_token = token_data["access_token"]
        claims = jwt.decode(new_token, options={"verify_signature": False})

        return ExchangedToken(
            access_token=new_token,
            audience=target_audience,
            subject=claims.get("sub", "unknown"),
            actor=claims.get("act", {}).get("sub", "unknown"),
            expires_at=claims.get("exp", 0),
            cached=False,
        )

    def _cache_key(self, subject_token: str, audience: str) -> str:
        """Generate a deterministic cache key from token JTI + audience."""
        try:
            claims = jwt.decode(subject_token, options={"verify_signature": False})
            jti = claims.get("jti", subject_token[:32])
        except Exception:
            jti = subject_token[:32]
        raw = f"{jti}:{audience}"
        return f"{self.cache_prefix}{hashlib.sha256(raw.encode()).hexdigest()[:24]}"

    @classmethod
    def from_keycloak(
        cls,
        realm_url: str,
        client_id: str,
        client_secret: str,
        redis_client: Optional[aioredis.Redis] = None,
        cache_ttl: int = 300,
    ) -> "TokenExchangeClient":
        """Create an exchange client configured for a Keycloak realm."""
        return cls(
            token_url=f"{realm_url}/protocol/openid-connect/token",
            client_id=client_id,
            client_secret=client_secret,
            redis_client=redis_client,
            cache_ttl=cache_ttl,
        )
