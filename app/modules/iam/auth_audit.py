"""Auth audit event helpers.

Thin wrappers around PlatformAuditService and TenantAuditService that
standardise table_name, actor_type, and record_id for each auth operation.

Both helpers call session.add() via the audit service, which is committed
as part of the surrounding transaction. No extra commit calls are needed.

table_name conventions:
  "platform_sessions" — session-scope events (login, refresh, logout, me)
  "platform_users"    — user-scope events (password_reset_requested/confirmed)
  "tenant_sessions"   — same as above for tenant side
  "tenant_users"      — same as above for tenant side
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from app.core.audit.service import PlatformAuditService, TenantAuditService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_NIL_UUID = uuid.UUID(int=0)  # record_id when no user is known (anonymous events)

_SESSION_OPERATIONS = frozenset({
    "login_success",
    "login_failed",
    "login_locked",
    "refresh",
    "logout",
    "me",
})


def _platform_table(operation: str, override: str | None) -> str:
    if override:
        return override
    return "platform_sessions" if operation in _SESSION_OPERATIONS else "platform_users"


def _tenant_table(operation: str, override: str | None) -> str:
    if override:
        return override
    return "tenant_sessions" if operation in _SESSION_OPERATIONS else "tenant_users"


async def write_platform_auth_event(
    *,
    db: AsyncSession,
    operation: str,
    actor_id: uuid.UUID | None,
    actor_label: str | None = None,
    after_state: dict[str, Any] | None = None,
    table_name: str | None = None,
) -> None:
    """Write a single platform auth audit row to platform.audit_log.

    Args:
        db:           Platform DB session (search_path=platform already set).
        operation:    Auth event type, e.g. "login_success", "login_failed".
        actor_id:     PlatformUser.id. Pass None for anonymous events.
        actor_label:  Email address of the actor (for human-readable audit trail).
        after_state:  Optional dict of event context (session_id, ip_address, etc.).
        table_name:   Override the auto-detected table name.
    """
    svc = PlatformAuditService(db)
    await svc.record(
        table_name=_platform_table(operation, table_name),
        record_id=actor_id if actor_id is not None else _NIL_UUID,
        operation=operation,
        actor_type="platform_user" if actor_id is not None else "anonymous",
        actor_id=actor_id,
        actor_label=actor_label,
        after_state=after_state,
    )


async def write_tenant_auth_event(
    *,
    db: AsyncSession,
    operation: str,
    actor_id: uuid.UUID | None,
    actor_label: str | None = None,
    tenant_slug: str | None = None,
    after_state: dict[str, Any] | None = None,
    table_name: str | None = None,
) -> None:
    """Write a single tenant auth audit row to the tenant audit_log.

    Args:
        db:           Tenant DB session (search_path set by middleware).
        operation:    Auth event type, e.g. "login_success", "me".
        actor_id:     TenantUser.id. Pass None for anonymous events.
        actor_label:  Email address of the actor.
        tenant_slug:  Tenant slug — appended to after_state for context.
        after_state:  Optional dict of event context.
        table_name:   Override the auto-detected table name.
    """
    svc = TenantAuditService(db)
    state: dict[str, Any] = dict(after_state or {})
    if tenant_slug:
        state["tenant"] = tenant_slug
    await svc.record(
        table_name=_tenant_table(operation, table_name),
        record_id=actor_id if actor_id is not None else _NIL_UUID,
        operation=operation,
        actor_type="tenant_user" if actor_id is not None else "anonymous",
        actor_id=actor_id,
        actor_label=actor_label,
        after_state=state if state else None,
    )
