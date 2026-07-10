"""NotificationService.publish — the ONLY path that creates notification_events.

Writes in the caller's transaction (the event row is the notification outbox).
Dispatch happens later via the beat job (see beat.py) — never here.
"""
from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003 (runtime use in signature)
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.notifications.catalog import BY_CODE, CHANNELS
from app.core.notifications.models import (
    NotificationTemplate,
    PlatformNotificationEvent,
    TenantNotificationEvent,
)

_log = structlog.get_logger(__name__)


class NotificationService:
    def __init__(self, session: AsyncSession, *, platform: bool | None = None) -> None:
        """`platform` overrides the session's is_platform inference — for
        platform-scoped services whose sessions may not carry the flag."""
        self._session = session
        is_platform = (
            platform
            if platform is not None
            else session.sync_session.info.get("is_platform", False)
        )
        self._model: type[PlatformNotificationEvent] | type[TenantNotificationEvent] = (
            PlatformNotificationEvent if is_platform else TenantNotificationEvent
        )

    async def publish(
        self,
        *,
        event_code: str,
        recipient_kind: str,
        recipient_user_id: uuid.UUID,
        recipient_email: str | None = None,
        recipient_phone: str | None = None,
        context: dict[str, Any],
        channels: list[str] | None = None,
        scheduled_at: datetime | None = None,
        dedupe_key: str | None = None,
    ) -> Any:
        spec = BY_CODE.get(event_code)
        if spec is None:
            raise ValueError(f"Unknown notification event_code '{event_code}'")
        if recipient_kind not in spec.recipient_kinds:
            raise ValueError(
                f"recipient kind '{recipient_kind}' is not allowed for '{event_code}'"
            )
        resolved_channels = (
            list(channels) if channels is not None else list(spec.default_channels)
        )
        for ch in resolved_channels:
            if ch not in CHANNELS:
                raise ValueError(f"Unknown channel '{ch}'")

        allowed_keys = await self._allowed_context_keys(event_code)
        if allowed_keys is not None:
            for key in context:
                if key not in allowed_keys:
                    raise ValueError(
                        f"context key '{key}' is not in the template allow-list "
                        f"for '{event_code}'"
                    )

        if dedupe_key is not None:
            existing = await self._session.scalar(
                select(self._model).where(self._model.dedupe_key == dedupe_key)
            )
            if existing is not None:
                return existing

        event = self._model(
            event_code=event_code,
            recipient_kind=recipient_kind,
            recipient_user_id=recipient_user_id,
            recipient_email=recipient_email,
            recipient_phone=recipient_phone,
            channels=resolved_channels,
            context=context,
            dedupe_key=dedupe_key,
        )
        if scheduled_at is not None:
            event.scheduled_at = scheduled_at
        self._session.add(event)
        await self._session.flush()
        _log.info(
            "notification.published",
            event_code=event_code,
            recipient_kind=recipient_kind,
            event_id=str(event.id),
        )
        return event

    async def _allowed_context_keys(self, event_code: str) -> set[str] | None:
        """Union of active templates' variables keys, or None when the code has
        no active templates at all (allow-list unenforceable — allow any context;
        strict validation resumes the moment templates exist)."""
        rows = list(
            (
                await self._session.execute(
                    select(NotificationTemplate.variables).where(
                        NotificationTemplate.code == event_code,
                        NotificationTemplate.is_active.is_(True),
                    )
                )
            ).scalars()
        )
        if not rows:
            return None
        allowed: set[str] = set()
        for variables in rows:
            allowed |= set(variables.keys())
        return allowed
