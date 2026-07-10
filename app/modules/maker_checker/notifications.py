"""Maker-checker lifecycle notifications (spec: notifications increment 2).

pending -> all eligible checkers except the maker; approved/rejected -> the
maker. A maker that is not a staff row (member-submitted operations) is
skipped silently — member-facing notices come from the owning module.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.notifications.service import NotificationService


async def _staff(session: AsyncSession) -> tuple[str, list[Any]]:
    if session.sync_session.info.get("is_platform", False):
        from app.platform_.models import PlatformUser  # noqa: PLC0415

        platform_rows = list(
            (
                await session.execute(
                    select(PlatformUser).where(
                        PlatformUser.is_active.is_(True),
                        PlatformUser.role.in_(("admin", "superuser")),
                    )
                )
            ).scalars()
        )
        return "platform_user", list(platform_rows)
    from app.modules.iam.tenant_users.models import TenantUser  # noqa: PLC0415

    tenant_rows = list(
        (
            await session.execute(
                select(TenantUser).where(
                    TenantUser.is_active.is_(True),
                    TenantUser.impersonation_id.is_(None),
                )
            )
        ).scalars()
    )
    return "tenant_user", list(tenant_rows)


async def notify_pending(session: AsyncSession, request: Any) -> None:
    kind, staff = await _staff(session)
    maker = next((u for u in staff if u.id == request.requested_by), None)
    label = maker.email if maker is not None else str(request.requested_by)
    svc = NotificationService(session)
    for user in staff:
        if user.id == request.requested_by:
            continue
        await svc.publish(
            event_code="maker_checker_pending",
            recipient_kind=kind,
            recipient_user_id=user.id,
            recipient_email=user.email,
            context={
                "operation_type": request.operation_type,
                "requested_by_label": label,
            },
            dedupe_key=f"mc_pending:{request.id}:{user.id}",
        )


async def notify_decided(
    session: AsyncSession, request: Any, *, approved: bool, reason: str | None
) -> None:
    kind, staff = await _staff(session)
    maker = next((u for u in staff if u.id == request.requested_by), None)
    if maker is None:
        return  # member-submitted (or departed) maker — owning module notifies
    if approved:
        code = "maker_checker_approved"
        context: dict[str, Any] = {"operation_type": request.operation_type}
        key = f"mc_approved:{request.id}"
    else:
        code = "maker_checker_rejected"
        context = {"operation_type": request.operation_type, "reason": reason or ""}
        key = f"mc_rejected:{request.id}"
    await NotificationService(session).publish(
        event_code=code,
        recipient_kind=kind,
        recipient_user_id=maker.id,
        recipient_email=maker.email,
        context=context,
        dedupe_key=key,
    )
