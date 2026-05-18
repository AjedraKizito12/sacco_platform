from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import event
from sqlalchemy.orm import Session, attributes


def _serialize(val: Any) -> Any:
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, datetime | date):
        return val.isoformat()
    if isinstance(val, Decimal):
        return str(val)
    return val


def _snapshot(mapper: Any, target: Any) -> dict[str, Any]:
    return {
        attr.key: _serialize(getattr(target, attr.key, None))
        for attr in mapper.column_attrs
    }


def _before_snapshot(mapper: Any, target: Any) -> dict[str, Any]:
    """Return pre-flush values for all columns (for update events)."""
    result: dict[str, Any] = {}
    for attr in mapper.column_attrs:
        hist = attributes.get_history(target, attr.key)
        old_val = hist.deleted[0] if hist.deleted else getattr(target, attr.key, None)
        result[attr.key] = _serialize(old_val)
    return result


def _actor_context() -> dict[str, Any]:
    ctx = structlog.contextvars.get_contextvars()
    return {
        "actor_type": ctx.get("actor_type", "system"),
        "actor_id": ctx.get("actor_id"),
        "actor_label": ctx.get("actor_label"),
        "request_id": ctx.get("request_id"),
    }


def _write_audit(
    target: Any,
    operation: str,
    before_state: dict[str, Any] | None,
    after_state: dict[str, Any] | None,
) -> None:
    from app.core.audit.models import PlatformAuditLog, TenantAuditLog

    session = Session.object_session(target)
    if session is None:
        return

    ctx = _actor_context()
    table_args = getattr(target.__class__, "__table_args__", None)
    is_platform = (
        isinstance(table_args, dict) and table_args.get("schema") == "platform"
    ) or (
        isinstance(table_args, tuple)
        and any(isinstance(a, dict) and a.get("schema") == "platform" for a in table_args)
    )

    model_cls = PlatformAuditLog if is_platform else TenantAuditLog
    row = model_cls(
        table_name=target.__tablename__,
        record_id=getattr(target, "id", None),
        operation=operation,
        before_state=before_state,
        after_state=after_state,
        occurred_at=datetime.now(UTC),
        **ctx,
    )
    session.add(row)


class AuditableMixin:
    """Mix into any SQLAlchemy model to auto-write audit_log on insert/update/delete."""

    @classmethod
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        @event.listens_for(cls, "after_insert")
        def after_insert(mapper: Any, connection: Any, target: Any) -> None:
            _write_audit(target, "insert", None, _snapshot(mapper, target))

        @event.listens_for(cls, "after_update")
        def after_update(mapper: Any, connection: Any, target: Any) -> None:
            before = _before_snapshot(mapper, target)
            after = _snapshot(mapper, target)
            _write_audit(target, "update", before, after)

        @event.listens_for(cls, "after_delete")
        def after_delete(mapper: Any, connection: Any, target: Any) -> None:
            _write_audit(target, "delete", _snapshot(mapper, target), None)
