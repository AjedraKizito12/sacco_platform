from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import event, insert
from sqlalchemy.orm import attributes


def _serialize(val: Any) -> Any:
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, datetime | date):
        return val.isoformat()
    if isinstance(val, Decimal):
        return str(val)
    if isinstance(val, bytes):
        return val.hex()
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
    raw_actor_id = ctx.get("actor_id")
    try:
        actor_id: uuid.UUID | None = (
            uuid.UUID(str(raw_actor_id)) if raw_actor_id is not None else None
        )
    except ValueError:
        actor_id = None
    return {
        "actor_type": ctx.get("actor_type", "system"),
        "actor_id": actor_id,
        "actor_label": ctx.get("actor_label"),
        "request_id": ctx.get("request_id"),
    }


def _get_record_id(mapper: Any, target: Any) -> uuid.UUID | None:
    """Return the primary-key UUID of *target*, reading directly from the
    instance rather than the identity map so that Python-side defaults
    (uuid.uuid4) are captured even before the mapper has registered the
    identity (which can be None immediately after after_insert fires)."""
    pk_attrs = [prop.key for prop in mapper.mapper.column_attrs
                if any(c.primary_key for c in prop.columns)]
    if not pk_attrs:
        return None
    raw = getattr(target, pk_attrs[0], None)
    if raw is None:
        return None
    try:
        return uuid.UUID(str(raw))
    except (ValueError, AttributeError):
        return None


def _write_audit(
    connection: Any,
    mapper: Any,
    target: Any,
    operation: str,
    before_state: dict[str, Any] | None,
    after_state: dict[str, Any] | None,
) -> None:
    """Insert an audit_log row using the *connection* of the in-flight flush.

    Insert is issued via Core-level ``connection.execute(insert(...))`` rather
    than ``session.add(...)``. The Session.add() path used to run inside
    after_insert / after_update / after_delete, which SQLAlchemy warns is
    'not currently supported within the execution stage of the flush
    process' and may produce inconsistent results. Going through the
    connection writes the row in the same transaction as the original
    change without re-entering the Session's flush state machine.
    """
    from app.core.audit.models import PlatformAuditLog, TenantAuditLog

    ctx = _actor_context()
    table_args = getattr(target.__class__, "__table_args__", None)
    is_platform = (
        isinstance(table_args, dict) and table_args.get("schema") == "platform"
    ) or (
        isinstance(table_args, tuple)
        and any(isinstance(a, dict) and a.get("schema") == "platform" for a in table_args)
    )

    record_id = _get_record_id(mapper, target)

    model_cls = PlatformAuditLog if is_platform else TenantAuditLog
    connection.execute(
        insert(model_cls).values(
            id=uuid.uuid4(),
            table_name=target.__tablename__,
            record_id=record_id,
            operation=operation,
            before_state=before_state,
            after_state=after_state,
            occurred_at=datetime.now(UTC),
            **ctx,
        )
    )


class AuditableMixin:
    """Mix into any SQLAlchemy model to auto-write audit_log on insert/update/delete."""

    @classmethod
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        @event.listens_for(cls, "after_insert")
        def after_insert(mapper: Any, connection: Any, target: Any) -> None:
            _write_audit(
                connection, mapper, target, "insert", None, _snapshot(mapper, target),
            )

        @event.listens_for(cls, "after_update")
        def after_update(mapper: Any, connection: Any, target: Any) -> None:
            before = _before_snapshot(mapper, target)
            after = _snapshot(mapper, target)
            _write_audit(connection, mapper, target, "update", before, after)

        @event.listens_for(cls, "after_delete")
        def after_delete(mapper: Any, connection: Any, target: Any) -> None:
            _write_audit(
                connection, mapper, target, "delete", _snapshot(mapper, target), None,
            )
