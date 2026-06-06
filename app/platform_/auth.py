"""Platform authentication dependency — stub or JWT depending on PLATFORM_AUTH_MODE.

When PLATFORM_AUTH_MODE=stub (default):
    get_current_platform_user validates X-Platform-Actor-ID against
    platform.platform_users but does NOT authenticate. Replace internals
    with JWT decode when IAM ships — the dependency signature stays unchanged.

When PLATFORM_AUTH_MODE=jwt:
    get_current_platform_user validates a Bearer JWT, checks session
    non-revocation, and returns the PlatformUser. Provided by
    app/modules/iam/dependencies.get_current_platform_user_jwt.

Production boot guard: APP_ENV=production + PLATFORM_AUTH_MODE=stub → crash.
"""
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

import structlog
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.core.config import get_settings
from app.core.db import get_platform_session
from app.platform_.models import PlatformUser

_log = structlog.get_logger(__name__)

PlatformSession = Annotated[AsyncSession, Depends(get_platform_session)]
ActorHeader = Annotated[str, Header(alias="X-Platform-Actor-ID")]

# ── Binding switch (runs at import time) ──────────────────────────────────────

_settings = get_settings()

if _settings.platform_auth_mode == "jwt":
    from app.modules.iam.dependencies import (
        get_current_platform_user_jwt as get_current_platform_user,
    )
else:
    async def get_current_platform_user(  # type: ignore[misc]
        x_platform_actor_id: ActorHeader,
        session: PlatformSession,
    ) -> PlatformUser:
        """Stub: parse X-Platform-Actor-ID, validate it exists and is active.

        Emits a WARNING on every call — this is intentional and noisy.
        Does NOT prove the caller is who the header claims.
        """
        _log.warning(
            "PLATFORM STUB AUTH: actor_id=%s — not production auth",
            x_platform_actor_id,
        )

        try:
            actor_id = uuid.UUID(x_platform_actor_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="Invalid X-Platform-Actor-ID: must be a UUID"
            ) from exc

        result = await session.execute(
            select(PlatformUser).where(PlatformUser.id == actor_id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise HTTPException(status_code=401, detail="Platform actor not found")

        if not user.is_active:
            raise HTTPException(status_code=403, detail="Platform actor is inactive")

        # Bind to structlog context vars so AuditableMixin picks up actor identity.
        structlog.contextvars.bind_contextvars(
            actor_type="platform_user",
            actor_id=str(user.id),
            actor_label=user.email,
        )

        return user


CurrentPlatformUser = Annotated[PlatformUser, Depends(get_current_platform_user)]


async def get_current_superuser(
    user: CurrentPlatformUser,
) -> PlatformUser:
    """Require is_superuser=True. Build on top of get_current_platform_user."""
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser required")
    return user


CurrentSuperuser = Annotated[PlatformUser, Depends(get_current_superuser)]


# ── Role hierarchy ────────────────────────────────────────────────────────────

_ROLE_RANK: dict[str, int] = {
    "superuser": 4,
    "admin": 3,
    "finance": 2,
    "support": 1,
}


def get_current_platform_user_with_role(
    role: str,
) -> Callable[[PlatformUser], Awaitable[PlatformUser]]:
    """Dep factory: returns a FastAPI dep requiring role rank >= ``role``.

    Use as::

        CurrentAdmin = Annotated[
            PlatformUser, Depends(get_current_platform_user_with_role("admin"))
        ]

    A user with role='admin' passes ``with_role('admin')``, ``with_role('finance')``,
    and ``with_role('support')`` but is rejected by ``with_role('superuser')``.

    Raises:
        ValueError: if ``role`` is not one of the four valid values
            (programmer error — fail fast at module import time).
    """
    if role not in _ROLE_RANK:
        raise ValueError(
            f"unknown role {role!r}; must be one of {sorted(_ROLE_RANK)}"
        )
    required_rank = _ROLE_RANK[role]

    async def _dep(
        user: CurrentPlatformUser,
    ) -> PlatformUser:
        user_rank = _ROLE_RANK.get(user.role, 0)
        # Backward compat: is_superuser=true overrides role rank.
        if user.is_superuser:
            user_rank = max(user_rank, _ROLE_RANK["superuser"])
        if user_rank < required_rank:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Requires role >= {role!r}; "
                    f"current role is {user.role!r}"
                ),
            )
        return user

    return _dep


# Pre-built dep shortcuts.
CurrentAdmin = Annotated[
    PlatformUser, Depends(get_current_platform_user_with_role("admin"))
]
CurrentFinance = Annotated[
    PlatformUser, Depends(get_current_platform_user_with_role("finance"))
]
CurrentSupport = Annotated[
    PlatformUser, Depends(get_current_platform_user_with_role("support"))
]


__all__ = [
    "CurrentAdmin",
    "CurrentFinance",
    "CurrentPlatformUser",
    "CurrentSuperuser",
    "CurrentSupport",
    "get_current_platform_user",
    "get_current_platform_user_with_role",
    "get_current_superuser",
]
