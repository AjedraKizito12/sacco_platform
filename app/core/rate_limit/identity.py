from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

import jwt as pyjwt
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.rate_limit.policies import Audience
from app.modules.iam.keys.service import KeyService
from app.modules.iam.tokens.service import get_unverified_kid

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    from fastapi import Request
    from sqlalchemy.ext.asyncio import AsyncSession

_JWK_CACHE_TTL_SECONDS = 300


@dataclass(frozen=True)
class RateLimitIdentity:
    key: str
    audience: Audience
    tenant_slug: str | None = None


def _map_audience(aud: str) -> Audience:
    """Map a verified JWT ``aud`` claim to a rate-limit :class:`Audience`.

    Unknown/unexpected values fall back to ``anonymous`` defensively — this
    function only ever runs on claims that already passed signature
    verification, but we never want a surprising ``aud`` value to grant an
    elevated rate-limit tier.
    """
    if aud == "platform":
        return "platform"
    if aud.startswith("tenant:"):
        return "tenant"
    if aud.startswith("member:"):
        return "member"
    return "anonymous"


def _tenant_slug_from_aud(aud: str) -> str | None:
    if aud.startswith("tenant:") or aud.startswith("member:"):
        _, _, slug = aud.partition(":")
        return slug or None
    return None


def _client_ip(request: object, *, trusted_proxy: bool) -> str:
    """Derive the client IP, honoring ``X-Forwarded-For`` only when the
    deployment's reverse proxy is trusted to set/overwrite that header.

    Never trust ``X-Forwarded-For`` from the open internet — it is
    caller-supplied and trivially spoofable when there is no trusted proxy
    in front of the app.
    """
    headers = request.headers  # type: ignore[attr-defined]
    if trusted_proxy:
        xff: str | None = headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
    # ``Request.client`` is ``Address | None`` and is legitimately ``None`` in
    # real deployments (unix sockets, some proxy/ASGI setups). Guard here so
    # ``_client_ip`` — and therefore ``derive_identity`` — can never raise into
    # the request path.
    client = request.client  # type: ignore[attr-defined]
    if client is None:
        return "unknown"
    host: str = client.host
    return host


async def _get_verification_key(
    kid: str,
    redis: Redis,
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
) -> tuple[bytes, str]:
    """Return ``(public_key_pem, algorithm)`` for *kid*, cached in Redis.

    Mirrors the cache pattern in ``app/core/db.py:_resolve_tenant_schema``:
    a short-TTL Redis cache in front of a DB lookup, to avoid opening a
    platform DB session on every rate-limited request. ``KeyService`` already
    keeps its own 60s in-process cache, but that cache is per-process and
    still requires a session to construct — this Redis layer is the one that
    actually saves the DB round trip.
    """
    cache_key = f"rl:jwk:{kid}"
    cached: bytes | None = await redis.get(cache_key)
    if cached is not None:
        payload = json.loads(cached)
        return payload["pem"].encode(), payload["alg"]

    async with session_factory() as session:
        public_pem, algorithm, _key_audience = await KeyService(
            session
        ).get_verification_key(kid)

    await redis.setex(
        cache_key,
        _JWK_CACHE_TTL_SECONDS,
        json.dumps({"pem": public_pem.decode(), "alg": algorithm}),
    )
    return public_pem, algorithm


async def derive_identity(
    request: Request,
    redis: Redis,
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
) -> RateLimitIdentity:
    """Derive the identity a request should be rate-limited under.

    Verified-JWT identity always wins over IP identity when a bearer token
    is present and verifies — this is the unspoofable path: a forged or
    tampered token can never pass signature verification, so it always
    falls through to IP-based identity instead of granting a forged
    authenticated identity's (usually higher) rate-limit tier.
    """
    trusted_proxy = get_settings().rate_limit_trusted_proxy
    auth_header = request.headers.get("authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return RateLimitIdentity(
            key=f"ip:{_client_ip(request, trusted_proxy=trusted_proxy)}",
            audience="anonymous",
        )

    try:
        kid = get_unverified_kid(token)
        public_pem, algorithm = await _get_verification_key(
            kid, redis, session_factory
        )
        claims = pyjwt.decode(
            token,
            public_pem,
            algorithms=[algorithm],
            options={"verify_aud": False},
        )
        sub = str(claims["sub"])
        aud = str(claims["aud"])
    except Exception:
        # Any failure — malformed token, unknown kid, bad signature, expired,
        # missing claims — falls through to IP identity. A forged token can
        # never reach this branch with a spoofed identity because it can't
        # pass signature verification above.
        return RateLimitIdentity(
            key=f"ip:{_client_ip(request, trusted_proxy=trusted_proxy)}",
            audience="anonymous",
        )

    audience = _map_audience(aud)
    return RateLimitIdentity(
        key=f"u:{audience}:{sub}",
        audience=audience,
        tenant_slug=_tenant_slug_from_aud(aud),
    )
