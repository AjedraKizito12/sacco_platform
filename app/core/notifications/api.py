"""Notifications HTTP APIs.

Self surface (feed / read / preferences) for the three audiences at their
conventional prefixes, plus the platform-admin template/event surface.
The self API touches only read_at and preferences; the admin resend endpoint
re-queues (the beat delivers) — nothing here marks an event sent.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_platform_session, get_tenant_session
from app.core.notifications.catalog import BY_CODE, CHANNELS
from app.core.notifications.models import (
    NotificationTemplate,
    PlatformNotificationEvent,
    PlatformNotificationPreference,
    TenantNotificationEvent,
    TenantNotificationPreference,
)
from app.core.notifications.renderer import render
from app.core.notifications.schemas import (
    NotificationEventAdminOut,
    NotificationFeedItemOut,
    NotificationPreferenceIn,
    NotificationPreferenceOut,
    NotificationTemplateIn,
    NotificationTemplateOut,
    NotificationTemplatePatch,
)
from app.modules.iam.dependencies import CurrentMember, CurrentTenantUser
from app.platform_.auth import CurrentAdmin, CurrentPlatformUser, CurrentSupport

TenantSession = Annotated[AsyncSession, Depends(get_tenant_session)]
PlatformSession = Annotated[AsyncSession, Depends(get_platform_session)]

platform_self_router = APIRouter(
    prefix="/platform/notifications/me", tags=["notifications"]
)
tenant_self_router = APIRouter(prefix="/notifications/me", tags=["notifications"])
member_self_router = APIRouter(
    prefix="/member/notifications/me", tags=["notifications"]
)
platform_admin_router = APIRouter(
    prefix="/platform/notifications", tags=["notifications-admin"]
)


# ── Shared self-surface implementation ───────────────────────────────────────


async def _feed(
    session: AsyncSession,
    model: Any,
    kind: str,
    user_id: uuid.UUID,
    *,
    unread_only: bool,
    limit: int,
    offset: int,
) -> list[NotificationFeedItemOut]:
    q = (
        select(model)
        .where(
            model.recipient_kind == kind,
            model.recipient_user_id == user_id,
            model.channels.any("in_app"),
        )
        .order_by(model.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if unread_only:
        q = q.where(model.read_at.is_(None))
    events = list((await session.execute(q)).scalars())

    codes = {e.event_code for e in events}
    templates: dict[str, NotificationTemplate] = {}
    if codes:
        rows = (
            await session.execute(
                select(NotificationTemplate).where(
                    NotificationTemplate.code.in_(codes),
                    NotificationTemplate.channel == "in_app",
                    NotificationTemplate.locale == "en",
                    NotificationTemplate.is_active.is_(True),
                )
            )
        ).scalars()
        templates = {t.code: t for t in rows}

    items: list[NotificationFeedItemOut] = []
    for event in events:
        template = templates.get(event.event_code)
        title, body = event.event_code, ""
        if template is not None:
            try:
                title = render(template.subject_template or "", event.context, html=False)
                body = render(template.body_text or "", event.context, html=False)
            except Exception:  # render error -> raw fallback, never 500 the feed
                title, body = event.event_code, ""
        items.append(
            NotificationFeedItemOut(
                id=event.id,
                event_code=event.event_code,
                title=title,
                body=body,
                status=event.status,
                created_at=event.created_at,
                read_at=event.read_at,
            )
        )
    return items


async def _mark_read(
    session: AsyncSession, model: Any, kind: str, user_id: uuid.UUID, event_id: uuid.UUID
) -> None:
    event = await session.get(model, event_id)
    if event is None or event.recipient_kind != kind or event.recipient_user_id != user_id:
        raise HTTPException(status_code=404, detail="Notification not found")
    if event.read_at is None:
        event.read_at = datetime.now(UTC)
        await session.flush()


async def _get_preferences(
    session: AsyncSession, model: Any, kind: str, user_id: uuid.UUID
) -> list[NotificationPreferenceOut]:
    rows = (
        await session.execute(
            select(model).where(
                model.recipient_kind == kind, model.user_id == user_id
            )
        )
    ).scalars()
    return [NotificationPreferenceOut.model_validate(r) for r in rows]


async def _put_preferences(
    session: AsyncSession,
    model: Any,
    kind: str,
    user_id: uuid.UUID,
    body: list[NotificationPreferenceIn],
) -> list[NotificationPreferenceOut]:
    for pref in body:
        if pref.event_code not in BY_CODE:
            raise HTTPException(
                status_code=422, detail=f"Unknown event_code '{pref.event_code}'"
            )
        if pref.channel not in CHANNELS:
            raise HTTPException(status_code=422, detail=f"Unknown channel '{pref.channel}'")
    for pref in body:
        existing = await session.scalar(
            select(model).where(
                model.recipient_kind == kind,
                model.user_id == user_id,
                model.event_code == pref.event_code,
                model.channel == pref.channel,
            )
        )
        if existing is None:
            session.add(
                model(
                    recipient_kind=kind,
                    user_id=user_id,
                    event_code=pref.event_code,
                    channel=pref.channel,
                    enabled=pref.enabled,
                )
            )
        else:
            existing.enabled = pref.enabled
    await session.flush()
    return await _get_preferences(session, model, kind, user_id)


# ── Platform self ────────────────────────────────────────────────────────────


@platform_self_router.get("", response_model=list[NotificationFeedItemOut])
async def platform_feed(
    session: PlatformSession,
    user: CurrentPlatformUser,
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[NotificationFeedItemOut]:
    return await _feed(
        session, PlatformNotificationEvent, "platform_user", user.id,
        unread_only=unread_only, limit=limit, offset=offset,
    )


@platform_self_router.post("/{event_id}/read")
async def platform_mark_read(
    event_id: uuid.UUID, session: PlatformSession, user: CurrentPlatformUser
) -> Response:
    await _mark_read(session, PlatformNotificationEvent, "platform_user", user.id, event_id)
    return Response(status_code=204)


@platform_self_router.get("/preferences", response_model=list[NotificationPreferenceOut])
async def platform_get_preferences(
    session: PlatformSession, user: CurrentPlatformUser
) -> list[NotificationPreferenceOut]:
    return await _get_preferences(
        session, PlatformNotificationPreference, "platform_user", user.id
    )


@platform_self_router.put("/preferences", response_model=list[NotificationPreferenceOut])
async def platform_put_preferences(
    body: list[NotificationPreferenceIn],
    session: PlatformSession,
    user: CurrentPlatformUser,
) -> list[NotificationPreferenceOut]:
    return await _put_preferences(
        session, PlatformNotificationPreference, "platform_user", user.id, body
    )


# ── Tenant operator self ─────────────────────────────────────────────────────


@tenant_self_router.get("", response_model=list[NotificationFeedItemOut])
async def tenant_feed(
    session: TenantSession,
    user: CurrentTenantUser,
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[NotificationFeedItemOut]:
    return await _feed(
        session, TenantNotificationEvent, "tenant_user", user.id,
        unread_only=unread_only, limit=limit, offset=offset,
    )


@tenant_self_router.post("/{event_id}/read")
async def tenant_mark_read(
    event_id: uuid.UUID, session: TenantSession, user: CurrentTenantUser
) -> Response:
    await _mark_read(session, TenantNotificationEvent, "tenant_user", user.id, event_id)
    return Response(status_code=204)


@tenant_self_router.get("/preferences", response_model=list[NotificationPreferenceOut])
async def tenant_get_preferences(
    session: TenantSession, user: CurrentTenantUser
) -> list[NotificationPreferenceOut]:
    return await _get_preferences(
        session, TenantNotificationPreference, "tenant_user", user.id
    )


@tenant_self_router.put("/preferences", response_model=list[NotificationPreferenceOut])
async def tenant_put_preferences(
    body: list[NotificationPreferenceIn],
    session: TenantSession,
    user: CurrentTenantUser,
) -> list[NotificationPreferenceOut]:
    return await _put_preferences(
        session, TenantNotificationPreference, "tenant_user", user.id, body
    )


# ── Member self ──────────────────────────────────────────────────────────────


@member_self_router.get("", response_model=list[NotificationFeedItemOut])
async def member_feed(
    session: TenantSession,
    member: CurrentMember,
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[NotificationFeedItemOut]:
    return await _feed(
        session, TenantNotificationEvent, "member", member.id,
        unread_only=unread_only, limit=limit, offset=offset,
    )


@member_self_router.post("/{event_id}/read")
async def member_mark_read(
    event_id: uuid.UUID, session: TenantSession, member: CurrentMember
) -> Response:
    await _mark_read(session, TenantNotificationEvent, "member", member.id, event_id)
    return Response(status_code=204)


@member_self_router.get("/preferences", response_model=list[NotificationPreferenceOut])
async def member_get_preferences(
    session: TenantSession, member: CurrentMember
) -> list[NotificationPreferenceOut]:
    return await _get_preferences(
        session, TenantNotificationPreference, "member", member.id
    )


@member_self_router.put("/preferences", response_model=list[NotificationPreferenceOut])
async def member_put_preferences(
    body: list[NotificationPreferenceIn],
    session: TenantSession,
    member: CurrentMember,
) -> list[NotificationPreferenceOut]:
    return await _put_preferences(
        session, TenantNotificationPreference, "member", member.id, body
    )


# ── Platform admin ───────────────────────────────────────────────────────────


@platform_admin_router.get("/templates", response_model=list[NotificationTemplateOut])
async def list_templates(
    session: PlatformSession, _user: CurrentSupport
) -> list[NotificationTemplateOut]:
    rows = (
        await session.execute(
            select(NotificationTemplate).order_by(
                NotificationTemplate.code, NotificationTemplate.channel
            )
        )
    ).scalars()
    return [NotificationTemplateOut.model_validate(t) for t in rows]


@platform_admin_router.post(
    "/templates", response_model=NotificationTemplateOut, status_code=201
)
async def create_template(
    body: NotificationTemplateIn, session: PlatformSession, _user: CurrentAdmin
) -> NotificationTemplateOut:
    if body.channel not in CHANNELS:
        raise HTTPException(status_code=422, detail=f"Unknown channel '{body.channel}'")
    template = NotificationTemplate(**body.model_dump())
    session.add(template)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Template ({body.code}, {body.channel}, {body.locale}) already exists",
        ) from exc
    return NotificationTemplateOut.model_validate(template)


@platform_admin_router.patch(
    "/templates/{template_id}", response_model=NotificationTemplateOut
)
async def patch_template(
    template_id: uuid.UUID,
    body: NotificationTemplatePatch,
    session: PlatformSession,
    _user: CurrentAdmin,
) -> NotificationTemplateOut:
    template = await session.get(NotificationTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    await session.flush()
    await session.refresh(template)
    return NotificationTemplateOut.model_validate(template)


@platform_admin_router.get("/events", response_model=list[NotificationEventAdminOut])
async def search_events(
    session: PlatformSession,
    _user: CurrentSupport,
    recipient_user_id: uuid.UUID | None = Query(default=None),
    event_code: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[NotificationEventAdminOut]:
    q = (
        select(PlatformNotificationEvent)
        .order_by(PlatformNotificationEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if recipient_user_id is not None:
        q = q.where(PlatformNotificationEvent.recipient_user_id == recipient_user_id)
    if event_code is not None:
        q = q.where(PlatformNotificationEvent.event_code == event_code)
    if status is not None:
        q = q.where(PlatformNotificationEvent.status == status)
    rows = (await session.execute(q)).scalars()
    return [NotificationEventAdminOut.model_validate(e) for e in rows]


@platform_admin_router.post(
    "/events/{event_id}/resend", response_model=NotificationEventAdminOut
)
async def resend_event(
    event_id: uuid.UUID, session: PlatformSession, _user: CurrentAdmin
) -> NotificationEventAdminOut:
    """Re-queue a non-queued event; the dispatch beat delivers it. The
    dispatcher's sent-channel guard prevents double sends."""
    event = await session.get(PlatformNotificationEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Notification event not found")
    if event.status == "queued":
        raise HTTPException(status_code=409, detail="Event is already queued")
    event.status = "queued"
    event.scheduled_at = datetime.now(UTC)
    await session.flush()
    return NotificationEventAdminOut.model_validate(event)
