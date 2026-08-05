"""ASGI middleware composing identity -> policy -> token-bucket rate limiting.

Registered in ``app/main.py`` so it runs INSIDE ``request_id_middleware``
(request id contextvars are already bound, so a 429's logs and response
still carry ``X-Request-ID``) but OUTSIDE routing/auth deps — a blocked
request never reaches a route handler.

Fails OPEN: any exception raised while talking to Redis (bucket check) is
caught and the request is allowed through, because a rate-limiter outage
must never take the platform down. The kill switch
(``settings.rate_limit_enabled``) makes this a pure pass-through with no
identity/policy work and no bucket call at all.
"""
from __future__ import annotations

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.observability import metrics
from app.core.rate_limit.bucket import check_bucket
from app.core.rate_limit.identity import derive_identity
from app.core.rate_limit.resolver import resolve_policy

_log = structlog.get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate-limits every request by verified-user or IP identity."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not get_settings().rate_limit_enabled:
            return await call_next(request)

        # Imported lazily so tests that repoint app.core.db.AsyncSessionFactory
        # (see tests/conftest.py's test_engine fixture) are picked up — a
        # module-scope import would bind the pre-test-engine reference.
        from app.core.db import AsyncSessionFactory

        redis = request.app.state.redis
        identity = await derive_identity(request, redis, AsyncSessionFactory)
        policy = await resolve_policy(
            request.url.path, identity, redis, AsyncSessionFactory
        )
        key = f"rl:{policy.name}:{identity.key}"

        try:
            result = await check_bucket(redis, key, policy)
        except Exception as exc:
            metrics.rate_limit_redis_health.set(0, {})
            _log.warning(
                "rate_limit.redis_unavailable",
                error=str(exc),
                path=request.url.path,
            )
            return await call_next(request)

        metrics.rate_limit_redis_health.set(1, {})

        if not result.allowed:
            metrics.rate_limit_blocks.add(
                1, {"policy": policy.name, "audience": identity.audience}
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after": result.reset,
                },
                headers={
                    "Retry-After": str(result.reset),
                    "X-RateLimit-Limit": str(result.limit),
                    "X-RateLimit-Remaining": str(result.remaining),
                    "X-RateLimit-Reset": str(result.reset),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        response.headers["X-RateLimit-Reset"] = str(result.reset)
        return response
