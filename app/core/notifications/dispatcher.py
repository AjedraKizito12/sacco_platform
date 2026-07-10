"""Dispatch one notification event to its channels.

Only the dispatcher/beat flips event.status. in_app succeeds by definition
(the event row IS the feed item) and writes no delivery row. A channel with
an existing 'sent' delivery is never re-sent.
"""
from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.notifications.models import (
    NotificationTemplate,
    PlatformNotificationDelivery,
    PlatformNotificationEvent,
    PlatformNotificationPreference,
    TenantNotificationDelivery,
    TenantNotificationPreference,
)
from app.core.notifications.providers import get_email_provider, get_sms_provider
from app.core.notifications.renderer import render

_log = structlog.get_logger(__name__)


async def dispatch_event(session: AsyncSession, event: Any) -> str:
    is_platform = isinstance(event, PlatformNotificationEvent)
    delivery_model: Any = (
        PlatformNotificationDelivery if is_platform else TenantNotificationDelivery
    )
    preference_model: Any = (
        PlatformNotificationPreference if is_platform else TenantNotificationPreference
    )

    disabled = {
        channel
        for channel in (
            await session.execute(
                select(preference_model.channel).where(
                    preference_model.recipient_kind == event.recipient_kind,
                    preference_model.user_id == event.recipient_user_id,
                    preference_model.event_code == event.event_code,
                    preference_model.enabled.is_(False),
                )
            )
        ).scalars()
    }
    resolved = [c for c in event.channels if c not in disabled]

    prior = list(
        (
            await session.execute(
                select(delivery_model).where(
                    delivery_model.notification_event_id == event.id
                )
            )
        ).scalars()
    )
    already_sent = {d.channel for d in prior if d.status == "sent"}
    attempts = {
        channel: sum(1 for d in prior if d.channel == channel)
        for channel in {d.channel for d in prior}
    }

    ok = 0
    failed = 0
    for channel in resolved:
        if channel == "in_app" or channel in already_sent:
            ok += 1
            continue
        outcome = await _send_channel(session, event, channel)
        session.add(
            delivery_model(
                notification_event_id=event.id,
                channel=channel,
                provider=outcome["provider"],
                attempt=attempts.get(channel, 0) + 1,
                status=outcome["status"],
                external_id=outcome["external_id"],
                error_message=outcome["error_message"],
            )
        )
        if outcome["status"] == "sent":
            ok += 1
        else:
            failed += 1

    if failed == 0:
        status = "sent"
    elif ok > 0:
        status = "partial"
    else:
        status = "failed"
    event.status = status
    await session.flush()
    _log.info("notification.dispatched", event_id=str(event.id), status=status)
    return status


async def _send_channel(session: AsyncSession, event: Any, channel: str) -> dict[str, Any]:
    template = await session.scalar(
        select(NotificationTemplate).where(
            NotificationTemplate.code == event.event_code,
            NotificationTemplate.channel == channel,
            NotificationTemplate.locale == "en",
            NotificationTemplate.is_active.is_(True),
        )
    )
    provider: Any = get_email_provider() if channel == "email" else get_sms_provider()
    if template is None:
        return _failure(provider.name, "no active template")
    try:
        if channel == "email":
            if not event.recipient_email:
                return _failure(provider.name, "no recipient email")
            external_id = await provider.send(
                to=event.recipient_email,
                subject=render(template.subject_template or "", event.context, html=False),
                text=render(template.body_text or "", event.context, html=False),
                html=(
                    render(template.body_html, event.context, html=True)
                    if template.body_html
                    else None
                ),
            )
        else:  # sms
            if not event.recipient_phone:
                return _failure(provider.name, "no recipient phone")
            external_id = await provider.send(
                to=event.recipient_phone,
                body=render(
                    template.sms_body or template.body_text or "",
                    event.context,
                    html=False,
                ),
            )
    except Exception as exc:  # provider or render failure — never crash the beat
        _log.warning("notification.channel_failed", channel=channel, error=str(exc))
        return _failure(provider.name, str(exc)[:500])
    return {
        "provider": provider.name,
        "status": "sent",
        "external_id": external_id,
        "error_message": None,
    }


def _failure(provider: str, message: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "status": "failed",
        "external_id": None,
        "error_message": message,
    }
