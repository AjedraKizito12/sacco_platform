"""Rate-limit error types.

``RateLimited`` is not raised into the ASGI stack — ``RateLimitMiddleware``
inspects the ``BucketResult`` directly and builds the 429 ``JSONResponse``
inline. This dataclass exists as a documented, typed carrier for the same
fields in case a future caller (e.g. the Task 6 read-only API) needs to
build an equivalent response shape outside the middleware.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimited:
    """Fields needed to build a 429 rate-limit-exceeded response."""

    limit: int
    remaining: int
    reset: int
    retry_after: int
