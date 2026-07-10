# Notifications Core Framework (Increment 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The complete notifications backend — tables, `NotificationService.publish`, null/log providers, sandboxed renderer, dispatcher, beat jobs, template seeds, and the self + platform-admin HTTP APIs — with zero call sites wired yet (that is increment 2).

**Architecture:** Per the approved spec (`docs/superpowers/specs/2026-07-10-notifications-framework-design.md`): `notification_events` is itself the notification outbox — `publish()` writes one `queued` row inside the caller's transaction; the `dispatch_pending_notifications` beat (30s) claims due rows with `FOR UPDATE SKIP LOCKED` and dispatches. `in_app` needs no provider (the event row is the feed item, `read_at` marks it read); email/SMS render via sandboxed Jinja2 and go to the settings-selected provider (`null` default, `log` writes delivery rows). Three recipient kinds (`platform_user | tenant_user | member`); 13 event codes; templates live in the platform schema only and are seeded by migration (tests seed via the same helper).

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic + Celery + Jinja2 (`SandboxedEnvironment`), pytest/httpx stub auth, structlog.

Branch: `feat/notifications-framework` (spec already committed on it).

## Global Constraints

- `NotificationService.publish()` is the ONLY path that creates `notification_events` rows. It writes in the caller's transaction; it never opens its own.
- Notifications never carry secrets (reset tokens, passwords) or sensitive PII. The template `variables` allow-list is enforced at publish: unknown context keys → `ValueError`.
- Providers are selected via settings (`notify_email_provider` / `notify_sms_provider`, default `"null"`). Adding a real provider must not change any call site or the dispatcher.
- The dispatcher/beat is the only code that flips event `status`; the self API touches only `read_at` and preferences.
- Dispatch semantics (spec-fixed): resolved channels = requested ∩ preference-enabled. `in_app` succeeds by definition, **no delivery row**. All resolved ok → `sent`; some → `partial`; none → `failed`; zero resolved channels → `sent`. Preference-disabled channels produce no delivery row. A channel with an existing `sent` delivery is never re-sent (retry idempotency).
- Preferences default to enabled — absence of a row means enabled.
- Audience path prefixes follow repo convention (spec refinement): platform `/platform/notifications/me*`, tenant operator `/notifications/me*`, member `/member/notifications/me*`. Cross-recipient access → 404.
- Dual-schema model pattern: shared mixins; `Platform*` classes with `{"schema": "platform"}`; tenant classes schema-less (search_path). Templates: platform schema ONLY.
- Migrations: `alembic/platform/versions/011_notifications.py`, `alembic/tenant/versions/019_notifications.py`.
- ruff + mypy (strict) clean; all DB access async; schemas in `schemas.py`, routers in `api.py`.

## Prerequisites

Branch `feat/notifications-framework` checked out. Docker Postgres test DB healthy.

## File Structure

```
app/core/notifications/__init__.py                (create, empty docstring module)
app/core/notifications/catalog.py                 (create: 13 event specs, pure)
app/core/notifications/models.py                  (create: mixins + platform/tenant models)
app/core/notifications/seed_templates.py          (create: DEFAULT_TEMPLATES + seed fn)
app/core/notifications/service.py                 (create: NotificationService.publish)
app/core/notifications/renderer.py                (create: sandboxed Jinja2)
app/core/notifications/providers/__init__.py      (create: get_email_provider/get_sms_provider)
app/core/notifications/providers/base.py          (create: interfaces)
app/core/notifications/providers/null.py          (create)
app/core/notifications/providers/log.py           (create)
app/core/notifications/dispatcher.py              (create)
app/core/notifications/beat.py                    (create: 3 beat tasks)
app/core/notifications/schemas.py                 (create: Pydantic)
app/core/notifications/api.py                     (create: 3 self routers + admin router)
alembic/platform/versions/011_notifications.py    (create)
alembic/tenant/versions/019_notifications.py      (create)
app/core/config.py                                (modify: +2 settings)
app/workers/celery_app.py                         (modify: include + 3 beat entries)
app/main.py                                       (modify: register 4 routers)
tests/conftest.py                                 (modify: +models import)
tests/core/notifications/__init__.py              (create)
tests/core/notifications/test_service.py          (create: catalog + seeds + publish)
tests/core/notifications/test_dispatch.py         (create: renderer/providers/dispatcher/beat)
tests/core/notifications/test_api.py              (create: self ×3 + admin)
CLAUDE.md                                         (modify: Task 8)
```

---

### Task 1: Catalog, models, migrations, conftest registration

**Files:**
- Create: `app/core/notifications/__init__.py`, `catalog.py`, `models.py`
- Create: `alembic/platform/versions/011_notifications.py`, `alembic/tenant/versions/019_notifications.py`
- Modify: `tests/conftest.py`
- Test: `tests/core/notifications/test_service.py` (create, catalog + model sections)

**Interfaces:**
- Produces (consumed by every later task):
  - `catalog.py`: `CHANNELS = ("email", "sms", "in_app")`, `RECIPIENT_KINDS = ("platform_user", "tenant_user", "member")`, `NotificationEventSpec(code, default_channels, recipient_kinds)` frozen dataclass, `NOTIFICATION_CATALOG: tuple[NotificationEventSpec, ...]` (13 codes), `spec_for(code) -> NotificationEventSpec` (raises `KeyError`).
  - `models.py`: `NotificationTemplate` (platform schema), `PlatformNotificationEvent`/`TenantNotificationEvent`, `PlatformNotificationDelivery`/`TenantNotificationDelivery`, `PlatformNotificationPreference`/`TenantNotificationPreference` via `NotificationEventMixin` / `NotificationDeliveryMixin` / `NotificationPreferenceMixin`. Event columns per spec incl. `recipient_kind`, `channels: ARRAY(Text)`, `context: JSONB`, `dedupe_key` (unique), `read_at`.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/notifications/__init__.py` (empty) and `tests/core/notifications/test_service.py`:

```python
"""Notifications: catalog, template seeds, and NotificationService.publish."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.notifications.catalog import (
    CHANNELS,
    NOTIFICATION_CATALOG,
    RECIPIENT_KINDS,
    spec_for,
)
from app.core.notifications.models import (
    PlatformNotificationEvent,
    TenantNotificationEvent,
)

SCHEMA = "tenant_test"

EXPECTED_CODES = (
    "password_reset",
    "maker_checker_pending",
    "maker_checker_approved",
    "maker_checker_rejected",
    "invoice_issued",
    "invoice_overdue",
    "subscription_suspended",
    "system_announcement",
    "member_activated",
    "kyc_submission_approved",
    "kyc_submission_rejected",
    "loan_application_approved",
    "loan_application_rejected",
)


@pytest.fixture
async def factory(test_engine: AsyncEngine):  # noqa: ANN201
    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    yield maker
    async with maker() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        for tbl in (
            f"{SCHEMA}.notification_deliveries",
            f"{SCHEMA}.notification_preferences",
            f"{SCHEMA}.notification_events",
            "platform.notification_deliveries",
            "platform.notification_preferences",
            "platform.notification_events",
        ):
            await s.execute(text(f"DELETE FROM {tbl}"))  # noqa: S608
        await s.commit()


async def _set_path(s: AsyncSession) -> None:
    await s.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))


def test_catalog_has_all_13_codes_with_valid_shapes() -> None:
    assert tuple(s.code for s in NOTIFICATION_CATALOG) == EXPECTED_CODES
    for spec in NOTIFICATION_CATALOG:
        assert spec.default_channels
        assert set(spec.default_channels) <= set(CHANNELS)
        assert spec.recipient_kinds
        assert set(spec.recipient_kinds) <= set(RECIPIENT_KINDS)
    assert spec_for("password_reset").code == "password_reset"
    with pytest.raises(KeyError):
        spec_for("nope")


async def test_event_rows_in_both_schemas_and_dedupe_unique(
    factory: async_sessionmaker,
) -> None:
    async with factory() as s:
        await _set_path(s)
        s.add(
            TenantNotificationEvent(
                event_code="system_announcement",
                recipient_kind="tenant_user",
                recipient_user_id=uuid.uuid4(),
                channels=["in_app"],
                context={"title": "hi"},
                dedupe_key="k-1",
            )
        )
        s.add(
            PlatformNotificationEvent(
                event_code="system_announcement",
                recipient_kind="platform_user",
                recipient_user_id=uuid.uuid4(),
                channels=["in_app"],
                context={},
            )
        )
        await s.flush()
        s.add(
            TenantNotificationEvent(
                event_code="system_announcement",
                recipient_kind="tenant_user",
                recipient_user_id=uuid.uuid4(),
                channels=["in_app"],
                context={},
                dedupe_key="k-1",
            )
        )
        with pytest.raises(IntegrityError):
            await s.flush()
        await s.rollback()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/notifications/test_service.py -q`
Expected: FAIL — `ModuleNotFoundError: app.core.notifications`.

- [ ] **Step 3: Write the implementation**

`app/core/notifications/__init__.py`:

```python
"""Cross-cutting notifications framework (SaaS launch Phase 3, increment 1)."""
```

`app/core/notifications/catalog.py`:

```python
"""Notification event taxonomy. Pure — no DB, no I/O.

Spec: docs/superpowers/specs/2026-07-10-notifications-framework-design.md.
"""
from __future__ import annotations

from dataclasses import dataclass

CHANNELS: tuple[str, ...] = ("email", "sms", "in_app")
RECIPIENT_KINDS: tuple[str, ...] = ("platform_user", "tenant_user", "member")

_STAFF = ("platform_user", "tenant_user")
_ALL = RECIPIENT_KINDS
_EMAIL_IN_APP = ("email", "in_app")


@dataclass(frozen=True)
class NotificationEventSpec:
    code: str
    default_channels: tuple[str, ...]
    recipient_kinds: tuple[str, ...]


NOTIFICATION_CATALOG: tuple[NotificationEventSpec, ...] = (
    NotificationEventSpec("password_reset", _EMAIL_IN_APP, _ALL),
    NotificationEventSpec("maker_checker_pending", _EMAIL_IN_APP, _STAFF),
    NotificationEventSpec("maker_checker_approved", _EMAIL_IN_APP, _STAFF),
    NotificationEventSpec("maker_checker_rejected", _EMAIL_IN_APP, _STAFF),
    NotificationEventSpec("invoice_issued", _EMAIL_IN_APP, ("tenant_user",)),
    NotificationEventSpec("invoice_overdue", _EMAIL_IN_APP, ("tenant_user",)),
    NotificationEventSpec("subscription_suspended", _EMAIL_IN_APP, ("tenant_user",)),
    NotificationEventSpec("system_announcement", _EMAIL_IN_APP, _ALL),
    NotificationEventSpec("member_activated", _EMAIL_IN_APP, ("member",)),
    NotificationEventSpec("kyc_submission_approved", _EMAIL_IN_APP, ("member",)),
    NotificationEventSpec("kyc_submission_rejected", _EMAIL_IN_APP, ("member",)),
    NotificationEventSpec("loan_application_approved", _EMAIL_IN_APP, ("member",)),
    NotificationEventSpec("loan_application_rejected", _EMAIL_IN_APP, ("member",)),
)

_BY_CODE = {s.code: s for s in NOTIFICATION_CATALOG}


def spec_for(code: str) -> NotificationEventSpec:
    return _BY_CODE[code]
```

`app/core/notifications/models.py`:

```python
"""Notification tables. Dual-schema pattern (see maker_checker.models).

Templates live in the PLATFORM schema only. Events / deliveries /
preferences exist in both schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003 (runtime use by SQLAlchemy)
from typing import Any

from sqlalchemy import (
    UUID,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    locale: Mapped[str] = mapped_column(Text, nullable=False, default="en")
    subject_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    sms_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    variables: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("code", "channel", "locale", name="uq_notification_templates_code_channel_locale"),
        {"schema": "platform"},
    )


class NotificationEventMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_code: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_kind: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    recipient_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    recipient_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    channels: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    dedupe_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    read_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class NotificationDeliveryMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class NotificationPreferenceMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_kind: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_code: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class TenantNotificationEvent(NotificationEventMixin, Base):
    __tablename__ = "notification_events"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_notification_events_dedupe_key"),
        Index("ix_notification_events_dispatch", "status", "scheduled_at"),
        Index("ix_notification_events_recipient", "recipient_kind", "recipient_user_id", "created_at"),
    )


class PlatformNotificationEvent(NotificationEventMixin, Base):
    __tablename__ = "notification_events"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_platform_notification_events_dedupe_key"),
        Index("ix_platform_notification_events_dispatch", "status", "scheduled_at"),
        Index("ix_platform_notification_events_recipient", "recipient_kind", "recipient_user_id", "created_at"),
        {"schema": "platform"},
    )


class TenantNotificationDelivery(NotificationDeliveryMixin, Base):
    __tablename__ = "notification_deliveries"
    notification_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notification_events.id", ondelete="CASCADE"), nullable=False
    )
    __table_args__ = (Index("ix_notification_deliveries_event", "notification_event_id"),)


class PlatformNotificationDelivery(NotificationDeliveryMixin, Base):
    __tablename__ = "notification_deliveries"
    notification_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform.notification_events.id", ondelete="CASCADE"), nullable=False
    )
    __table_args__ = (
        Index("ix_platform_notification_deliveries_event", "notification_event_id"),
        {"schema": "platform"},
    )


class TenantNotificationPreference(NotificationPreferenceMixin, Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint(
            "recipient_kind", "user_id", "event_code", "channel",
            name="uq_notification_preferences_scope",
        ),
    )


class PlatformNotificationPreference(NotificationPreferenceMixin, Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint(
            "recipient_kind", "user_id", "event_code", "channel",
            name="uq_platform_notification_preferences_scope",
        ),
        {"schema": "platform"},
    )
```

Migrations — `alembic/platform/versions/011_notifications.py` creates
`platform.notification_templates` (+ unique), `platform.notification_events`
(+ dedupe unique + the 2 indexes), `platform.notification_deliveries`
(FK CASCADE + index), `platform.notification_preferences` (+ unique) — column
lists exactly mirror the models above (`sa.Column(...)`, `postgresql.UUID/JSONB/ARRAY(sa.Text())`,
`sa.func.now()` server defaults). It also seeds templates (Task 2 adds the import +
`op.bulk_insert`). `alembic/tenant/versions/019_notifications.py` (down_revision "018")
creates the three tenant tables identically but schema-less. Downgrades drop in reverse
order. Write both files fully — no schema drift from the models; `revision = "011"` /
`down_revision = "010"` for platform.

In `tests/conftest.py`, add to the model-import block:

```python
    import app.core.notifications.models  # noqa: F401 — registers notification tables in Base.metadata
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/notifications/test_service.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Lint, typecheck, commit**

`python -m ruff check app/ tests/ && python -m mypy app/` → clean.

```bash
git add app/core/notifications alembic tests/conftest.py tests/core/notifications
git commit -m "feat(notifications): catalog, dual-schema models, migrations 011/019"
```

---

### Task 2: Default templates + seed helper

**Files:**
- Create: `app/core/notifications/seed_templates.py`
- Modify: `alembic/platform/versions/011_notifications.py` (add seed inserts)
- Test: `tests/core/notifications/test_service.py` (append)

**Interfaces:**
- Produces: `DEFAULT_TEMPLATES: tuple[dict, ...]` (one dict per (code, channel) pair: keys `code, channel, locale, subject_template, body_html, body_text, sms_body, variables`) and `async seed_default_templates(session) -> int` (idempotent upsert-by-(code,channel,locale), returns inserted count). Consumed by the migration, tests, and Task 5's renderer lookups.

- [ ] **Step 1: Write the failing tests**

Append to `tests/core/notifications/test_service.py`:

```python
from app.core.notifications.seed_templates import (  # noqa: E402
    DEFAULT_TEMPLATES,
    seed_default_templates,
)


def test_default_templates_cover_every_catalog_default_channel() -> None:
    pairs = {(t["code"], t["channel"]) for t in DEFAULT_TEMPLATES}
    for spec in NOTIFICATION_CATALOG:
        for channel in spec.default_channels:
            assert (spec.code, channel) in pairs, (spec.code, channel)
    for t in DEFAULT_TEMPLATES:
        assert isinstance(t["variables"], dict)
        if t["channel"] == "email":
            assert t["subject_template"] and t["body_text"]
        if t["channel"] == "in_app":
            assert t["subject_template"] and t["body_text"]


async def test_seed_is_idempotent(factory: async_sessionmaker) -> None:
    async with factory() as s:
        await _set_path(s)
        first = await seed_default_templates(s)
        again = await seed_default_templates(s)
        await s.commit()
    assert first >= len(DEFAULT_TEMPLATES) or first == 0  # fresh DB: all inserted; CI reruns: 0
    assert again == 0
```

(Note: the platform test schema persists across test files in a session — the
seed may already have run; the assertion tolerates both.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/notifications/test_service.py -q`
Expected: FAIL — `ModuleNotFoundError: seed_templates`.

- [ ] **Step 3: Write the implementation**

`app/core/notifications/seed_templates.py` — build `DEFAULT_TEMPLATES`
programmatically from the catalog so coverage is total by construction:

```python
"""Default notification templates (locale 'en') for every catalog default channel.

The platform migration inserts these; tests (which create tables via
Base.metadata, not alembic) call seed_default_templates() directly.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.notifications.catalog import NOTIFICATION_CATALOG
from app.core.notifications.models import NotificationTemplate

_TITLES: dict[str, str] = {
    "password_reset": "Password reset requested",
    "maker_checker_pending": "Approval needed: {{ operation_type }}",
    "maker_checker_approved": "Approved: {{ operation_type }}",
    "maker_checker_rejected": "Rejected: {{ operation_type }}",
    "invoice_issued": "Invoice {{ invoice_number }} issued",
    "invoice_overdue": "Invoice {{ invoice_number }} is overdue",
    "subscription_suspended": "Your subscription is suspended",
    "system_announcement": "{{ title }}",
    "member_activated": "Welcome — your membership is active",
    "kyc_submission_approved": "Your KYC details were approved",
    "kyc_submission_rejected": "Your KYC submission needs changes",
    "loan_application_approved": "Your loan application was approved",
    "loan_application_rejected": "Your loan application was declined",
}

_BODIES: dict[str, str] = {
    "password_reset": "A password reset was requested for your account. If this wasn't you, contact support.",
    "maker_checker_pending": "{{ operation_type }} requested by {{ requested_by_label }} is waiting for approval.",
    "maker_checker_approved": "Your {{ operation_type }} request was approved.",
    "maker_checker_rejected": "Your {{ operation_type }} request was rejected: {{ reason }}",
    "invoice_issued": "Invoice {{ invoice_number }} for {{ amount }} {{ currency }} was issued. Due {{ due_date }}.",
    "invoice_overdue": "Invoice {{ invoice_number }} for {{ amount }} {{ currency }} is overdue. Please arrange payment.",
    "subscription_suspended": "Your SACCO's subscription is suspended. Contact the platform administrator.",
    "system_announcement": "{{ body }}",
    "member_activated": "Hello {{ full_name }}, your membership {{ member_number }} is now active.",
    "kyc_submission_approved": "Your submitted KYC details were reviewed and applied to your member record.",
    "kyc_submission_rejected": "Your KYC submission was rejected: {{ reason }}. Please review and resubmit.",
    "loan_application_approved": "Your loan application for {{ amount }} was approved.",
    "loan_application_rejected": "Your loan application was declined: {{ reason }}",
}

_VARIABLES: dict[str, dict[str, str]] = {
    "password_reset": {},
    "maker_checker_pending": {
        "operation_type": "operation code", "requested_by_label": "maker display name",
    },
    "maker_checker_approved": {"operation_type": "operation code"},
    "maker_checker_rejected": {"operation_type": "operation code", "reason": "rejection reason"},
    "invoice_issued": {
        "invoice_number": "e.g. INV-2026-000001", "amount": "formatted amount",
        "currency": "ISO code", "due_date": "YYYY-MM-DD",
    },
    "invoice_overdue": {
        "invoice_number": "e.g. INV-2026-000001", "amount": "formatted amount",
        "currency": "ISO code",
    },
    "subscription_suspended": {},
    "system_announcement": {"title": "announcement title", "body": "announcement body"},
    "member_activated": {"full_name": "member name", "member_number": "member number"},
    "kyc_submission_approved": {},
    "kyc_submission_rejected": {"reason": "reviewer's reason"},
    "loan_application_approved": {"amount": "approved amount"},
    "loan_application_rejected": {"reason": "rejection reason"},
}


def _build() -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for spec in NOTIFICATION_CATALOG:
        for channel in spec.default_channels:
            rows.append(
                {
                    "code": spec.code,
                    "channel": channel,
                    "locale": "en",
                    "subject_template": _TITLES[spec.code],
                    "body_html": None,
                    "body_text": _BODIES[spec.code],
                    "sms_body": _BODIES[spec.code] if channel == "sms" else None,
                    "variables": _VARIABLES[spec.code],
                }
            )
    return tuple(rows)


DEFAULT_TEMPLATES: tuple[dict[str, Any], ...] = _build()


async def seed_default_templates(session: AsyncSession) -> int:
    """Insert any missing default templates. Idempotent; returns inserted count."""
    existing = {
        (code, channel, locale)
        for code, channel, locale in (
            await session.execute(
                select(
                    NotificationTemplate.code,
                    NotificationTemplate.channel,
                    NotificationTemplate.locale,
                )
            )
        ).all()
    }
    inserted = 0
    for row in DEFAULT_TEMPLATES:
        if (row["code"], row["channel"], row["locale"]) in existing:
            continue
        session.add(NotificationTemplate(**row))
        inserted += 1
    await session.flush()
    return inserted
```

In the platform migration's `upgrade()`, after creating the tables, insert the
same rows with `op.bulk_insert` against a lightweight `sa.table(...)` definition
built from `DEFAULT_TEMPLATES` (import it from `app.core.notifications.seed_templates`;
add `id=uuid.uuid4()` per row and serialize `variables` with `json.dumps` if needed
by the dialect — use `postgresql.JSONB` in the table stub so dicts pass through).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/notifications/test_service.py -q` → PASS (4 tests).

- [ ] **Step 5: Lint, typecheck, commit**

```bash
git add app/core/notifications/seed_templates.py alembic/platform/versions/011_notifications.py tests/core/notifications/test_service.py
git commit -m "feat(notifications): default template seeds (13 codes × default channels)"
```

---

### Task 3: `NotificationService.publish`

**Files:**
- Create: `app/core/notifications/service.py`
- Test: `tests/core/notifications/test_service.py` (append)

**Interfaces:**
- Consumes: catalog, models, seeded templates (for the `variables` allow-list).
- Produces: `NotificationService(session).publish(*, event_code, recipient_kind, recipient_user_id, recipient_email=None, recipient_phone=None, context, channels=None, scheduled_at=None, dedupe_key=None) -> NotificationEvent-model-instance`. Picks Platform vs Tenant model via `session.sync_session.info["is_platform"]` (same convention as `EventPublisher`/`ApprovalService`). Raises `ValueError` on: unknown code, kind not allowed for code, channel not in `CHANNELS`, context key not in the union of active templates' `variables` for the code. Idempotent on `dedupe_key` (returns existing row).

- [ ] **Step 1: Write the failing tests**

Append to `tests/core/notifications/test_service.py`:

```python
from app.core.notifications.service import NotificationService  # noqa: E402


@pytest.fixture
async def seeded(factory: async_sessionmaker) -> None:
    async with factory() as s:
        await _set_path(s)
        await seed_default_templates(s)
        await s.commit()


async def test_publish_writes_queued_event_in_callers_txn(
    factory: async_sessionmaker, seeded: None
) -> None:
    user_id = uuid.uuid4()
    async with factory() as s:
        await _set_path(s)
        event = await NotificationService(s).publish(
            event_code="system_announcement",
            recipient_kind="tenant_user",
            recipient_user_id=user_id,
            recipient_email="op@example.com",
            context={"title": "Maintenance", "body": "Tonight 22:00"},
        )
        assert event.status == "queued"
        assert sorted(event.channels) == ["email", "in_app"]  # catalog defaults
        await s.commit()
    async with factory() as s:
        await _set_path(s)
        row = await s.get(TenantNotificationEvent, event.id)
    assert row is not None
    assert row.recipient_email == "op@example.com"


async def test_publish_platform_session_uses_platform_table(
    test_engine: AsyncEngine, factory: async_sessionmaker, seeded: None
) -> None:
    async with factory() as s:
        s.sync_session.info["is_platform"] = True
        await _set_path(s)
        event = await NotificationService(s).publish(
            event_code="system_announcement",
            recipient_kind="platform_user",
            recipient_user_id=uuid.uuid4(),
            context={"title": "t", "body": "b"},
        )
        await s.commit()
    async with factory() as s:
        await _set_path(s)
        assert await s.get(PlatformNotificationEvent, event.id) is not None


async def test_publish_validation_errors(
    factory: async_sessionmaker, seeded: None
) -> None:
    async with factory() as s:
        await _set_path(s)
        svc = NotificationService(s)
        with pytest.raises(ValueError, match="Unknown"):
            await svc.publish(
                event_code="nope", recipient_kind="member",
                recipient_user_id=uuid.uuid4(), context={},
            )
        with pytest.raises(ValueError, match="recipient kind"):
            await svc.publish(
                event_code="invoice_issued", recipient_kind="member",
                recipient_user_id=uuid.uuid4(), context={},
            )
        with pytest.raises(ValueError, match="channel"):
            await svc.publish(
                event_code="system_announcement", recipient_kind="member",
                recipient_user_id=uuid.uuid4(), context={}, channels=["pigeon"],
            )
        with pytest.raises(ValueError, match="context key"):
            await svc.publish(
                event_code="system_announcement", recipient_kind="member",
                recipient_user_id=uuid.uuid4(),
                context={"title": "x", "body": "y", "national_id": "SECRET"},
            )
        await s.rollback()


async def test_publish_dedupe_key_is_idempotent(
    factory: async_sessionmaker, seeded: None
) -> None:
    key = f"test-{uuid.uuid4()}"
    async with factory() as s:
        await _set_path(s)
        svc = NotificationService(s)
        first = await svc.publish(
            event_code="system_announcement", recipient_kind="member",
            recipient_user_id=uuid.uuid4(), context={"title": "a", "body": "b"},
            dedupe_key=key,
        )
        second = await svc.publish(
            event_code="system_announcement", recipient_kind="member",
            recipient_user_id=uuid.uuid4(), context={"title": "a", "body": "b"},
            dedupe_key=key,
        )
        await s.commit()
    assert second.id == first.id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/notifications/test_service.py -q` → FAIL (`No module named ...service`).

- [ ] **Step 3: Write the implementation**

`app/core/notifications/service.py`:

```python
"""NotificationService.publish — the ONLY path that creates notification_events.

Writes in the caller's transaction (the event row is the notification outbox).
Dispatch happens later via the beat job (see beat.py) — never here.
"""
from __future__ import annotations

import uuid
from datetime import datetime
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
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        is_platform = session.sync_session.info.get("is_platform", False)
        self._model = PlatformNotificationEvent if is_platform else TenantNotificationEvent

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
        resolved_channels = list(channels) if channels is not None else list(spec.default_channels)
        for ch in resolved_channels:
            if ch not in CHANNELS:
                raise ValueError(f"Unknown channel '{ch}'")

        allowed_keys = await self._allowed_context_keys(event_code)
        for key in context:
            if key not in allowed_keys:
                raise ValueError(
                    f"context key '{key}' is not in the template allow-list for '{event_code}'"
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

    async def _allowed_context_keys(self, event_code: str) -> set[str]:
        rows = (
            await self._session.execute(
                select(NotificationTemplate.variables).where(
                    NotificationTemplate.code == event_code,
                    NotificationTemplate.is_active.is_(True),
                )
            )
        ).scalars()
        allowed: set[str] = set()
        for variables in rows:
            allowed |= set(variables.keys())
        return allowed
```

Also rename `catalog.py`'s `_BY_CODE` to public `BY_CODE` (update `spec_for` to use
it) — the service imports it, and importing an underscore name cross-module fails
ruff. Keep `spec_for` as the documented accessor; `BY_CODE` serves the `.get()` case.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/notifications/test_service.py -q` → PASS (9 tests).

- [ ] **Step 5: Lint, typecheck, commit**

```bash
git add app/core/notifications tests/core/notifications/test_service.py
git commit -m "feat(notifications): NotificationService.publish (validated, dedupe-idempotent)"
```

---

### Task 4: Renderer + providers + settings

**Files:**
- Create: `app/core/notifications/renderer.py`, `providers/__init__.py`, `providers/base.py`, `providers/null.py`, `providers/log.py`
- Modify: `app/core/config.py`
- Test: `tests/core/notifications/test_dispatch.py` (create — renderer/provider sections)

**Interfaces:**
- Produces (consumed by Task 5):
  - `renderer.render(template_str: str, context: dict, *, html: bool) -> str` — sandboxed Jinja2; `html=True` autoescapes.
  - `providers.base.EmailProvider` (`async send(self, *, to: str, subject: str, text: str, html: str | None) -> str | None`) and `SMSProvider` (`async send(self, *, to: str, body: str) -> str | None`); return = external id, raise = failure.
  - `NullEmailProvider/NullSMSProvider` (name `"null"`), `LogEmailProvider/LogSMSProvider` (name `"log"`; structlog info line). Each class has `name: str` class attr.
  - `providers.get_email_provider() -> EmailProvider`, `get_sms_provider() -> SMSProvider` reading `get_settings().notify_email_provider` / `.notify_sms_provider` (`"null"` default; unknown value → `ValueError` at call time).
  - Settings fields: `notify_email_provider: str = "null"`, `notify_sms_provider: str = "null"` (place next to the auth-mode settings in `app/core/config.py`).

- [ ] **Step 1: Write the failing tests**

Create `tests/core/notifications/test_dispatch.py`:

```python
"""Notifications: renderer, providers, dispatcher, beat."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.notifications.renderer import render

SCHEMA = "tenant_test"


def test_render_text_and_html_escaping() -> None:
    assert render("Hi {{ name }}", {"name": "Ada"}, html=False) == "Hi Ada"
    assert render("<b>{{ v }}</b>", {"v": "<x>"}, html=True) == "<b>&lt;x&gt;</b>"
    assert render("{{ v }}", {"v": "<x>"}, html=False) == "<x>"


def test_render_is_sandboxed() -> None:
    with pytest.raises(Exception):  # noqa: B017 — SecurityError from the sandbox
        render("{{ ''.__class__.__mro__ }}", {}, html=False)


async def test_null_and_log_providers() -> None:
    from app.core.notifications.providers.log import LogEmailProvider, LogSMSProvider
    from app.core.notifications.providers.null import NullEmailProvider, NullSMSProvider

    assert NullEmailProvider.name == "null"
    assert LogEmailProvider.name == "log"
    assert await NullEmailProvider().send(to="a@b.c", subject="s", text="t", html=None) is None
    assert await NullSMSProvider().send(to="+256", body="b") is None
    assert await LogEmailProvider().send(to="a@b.c", subject="s", text="t", html=None)
    assert await LogSMSProvider().send(to="+256", body="b")


def test_provider_factory_defaults_to_null() -> None:
    from app.core.notifications import providers
    from app.core.notifications.providers.null import NullEmailProvider

    assert isinstance(providers.get_email_provider(), NullEmailProvider)
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/core/notifications/test_dispatch.py -q` → FAIL (module missing).

- [ ] **Step 3: Write the implementation**

`renderer.py`:

```python
"""Sandboxed Jinja2 rendering for notification templates."""
from __future__ import annotations

from typing import Any

from jinja2.sandbox import SandboxedEnvironment

_HTML_ENV = SandboxedEnvironment(autoescape=True)
_TEXT_ENV = SandboxedEnvironment(autoescape=False)  # noqa: S701 — plain text/sms output


def render(template_str: str, context: dict[str, Any], *, html: bool) -> str:
    env = _HTML_ENV if html else _TEXT_ENV
    return env.from_string(template_str).render(**context)
```

`providers/base.py`:

```python
"""Provider interfaces. Return value = provider external id (or None); raise = failure."""
from __future__ import annotations

from abc import ABC, abstractmethod


class EmailProvider(ABC):
    name: str

    @abstractmethod
    async def send(self, *, to: str, subject: str, text: str, html: str | None) -> str | None: ...


class SMSProvider(ABC):
    name: str

    @abstractmethod
    async def send(self, *, to: str, body: str) -> str | None: ...
```

`providers/null.py`:

```python
"""No-op providers — v1 default. Nothing leaves the system."""
from __future__ import annotations

from app.core.notifications.providers.base import EmailProvider, SMSProvider


class NullEmailProvider(EmailProvider):
    name = "null"

    async def send(self, *, to: str, subject: str, text: str, html: str | None) -> str | None:
        return None


class NullSMSProvider(SMSProvider):
    name = "null"

    async def send(self, *, to: str, body: str) -> str | None:
        return None
```

`providers/log.py`:

```python
"""Log providers — write a structlog line; useful in closed beta and tests."""
from __future__ import annotations

import uuid

import structlog

from app.core.notifications.providers.base import EmailProvider, SMSProvider

_log = structlog.get_logger(__name__)


class LogEmailProvider(EmailProvider):
    name = "log"

    async def send(self, *, to: str, subject: str, text: str, html: str | None) -> str | None:
        external_id = f"log-{uuid.uuid4()}"
        _log.info("notification.email", to=to, subject=subject, external_id=external_id)
        return external_id


class LogSMSProvider(SMSProvider):
    name = "log"

    async def send(self, *, to: str, body: str) -> str | None:
        external_id = f"log-{uuid.uuid4()}"
        _log.info("notification.sms", to=to, external_id=external_id)
        return external_id
```

`providers/__init__.py`:

```python
"""Provider selection via settings. 'null' is the v1 default everywhere."""
from __future__ import annotations

from app.core.config import get_settings
from app.core.notifications.providers.base import EmailProvider, SMSProvider
from app.core.notifications.providers.log import LogEmailProvider, LogSMSProvider
from app.core.notifications.providers.null import NullEmailProvider, NullSMSProvider

_EMAIL: dict[str, type[EmailProvider]] = {"null": NullEmailProvider, "log": LogEmailProvider}
_SMS: dict[str, type[SMSProvider]] = {"null": NullSMSProvider, "log": LogSMSProvider}


def get_email_provider() -> EmailProvider:
    name = get_settings().notify_email_provider
    try:
        return _EMAIL[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown email provider '{name}'") from exc


def get_sms_provider() -> SMSProvider:
    name = get_settings().notify_sms_provider
    try:
        return _SMS[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown SMS provider '{name}'") from exc
```

`app/core/config.py`: add near the auth-mode fields:

```python
    # Notifications (Phase 3). 'null' = no delivery (v1 default); 'log' = structlog.
    notify_email_provider: str = "null"
    notify_sms_provider: str = "null"
```

- [ ] **Step 4: Run to verify pass** — `python -m pytest tests/core/notifications/test_dispatch.py -q` → PASS (5 tests).

- [ ] **Step 5: Lint, typecheck, commit**

```bash
git add app/core/notifications app/core/config.py tests/core/notifications/test_dispatch.py
git commit -m "feat(notifications): sandboxed renderer + null/log providers + settings"
```

---

### Task 5: Dispatcher

**Files:**
- Create: `app/core/notifications/dispatcher.py`
- Test: `tests/core/notifications/test_dispatch.py` (append)

**Interfaces:**
- Consumes: renderer, providers, models, Task 2 seeds.
- Produces: `async dispatch_event(session, event) -> str` (returns the final status). Behaviour per Global Constraints. Delivery model chosen to match the event model (platform vs tenant). Template lookup: `(code, channel, locale='en', is_active)`. Missing template / missing recipient address → failed delivery row with `error_message`; provider exception → failed delivery row; channel with an existing `sent` delivery is skipped (counts as ok). `attempt` = previous attempts for that channel + 1.

- [ ] **Step 1: Write the failing tests**

Append to `test_dispatch.py` (fixtures: reuse a `factory` + `_set_path` + seeded templates exactly like `test_service.py` — copy those three fixtures/helpers into this file, plus the same table cleanup):

```python
from app.core.notifications.dispatcher import dispatch_event  # noqa: E402
from app.core.notifications.models import (  # noqa: E402
    TenantNotificationDelivery,
    TenantNotificationEvent,
    TenantNotificationPreference,
)
from app.core.notifications.seed_templates import seed_default_templates  # noqa: E402
from app.core.notifications.service import NotificationService  # noqa: E402


async def _publish(s: AsyncSession, **overrides):  # noqa: ANN003, ANN202
    kwargs: dict = {
        "event_code": "system_announcement",
        "recipient_kind": "tenant_user",
        "recipient_user_id": uuid.uuid4(),
        "recipient_email": "op@example.com",
        "context": {"title": "T", "body": "B"},
    }
    kwargs.update(overrides)
    return await NotificationService(s).publish(**kwargs)


async def test_dispatch_in_app_plus_null_email(factory, seeded) -> None:  # noqa: ANN001
    async with factory() as s:
        await _set_path(s)
        event = await _publish(s)
        status = await dispatch_event(s, event)
        await s.commit()
    assert status == "sent"
    async with factory() as s:
        await _set_path(s)
        deliveries = list(
            (await s.execute(select(TenantNotificationDelivery))).scalars()
        )
    # in_app writes NO delivery row; null email writes one 'sent' row.
    assert [d.channel for d in deliveries] == ["email"]
    assert deliveries[0].provider == "null"
    assert deliveries[0].status == "sent"


async def test_dispatch_preference_disabled_email(factory, seeded) -> None:  # noqa: ANN001
    user_id = uuid.uuid4()
    async with factory() as s:
        await _set_path(s)
        s.add(
            TenantNotificationPreference(
                recipient_kind="tenant_user", user_id=user_id,
                event_code="system_announcement", channel="email", enabled=False,
            )
        )
        event = await _publish(s, recipient_user_id=user_id)
        status = await dispatch_event(s, event)
        await s.commit()
    assert status == "sent"  # in_app remains; email skipped, no delivery row
    async with factory() as s:
        await _set_path(s)
        assert (await s.execute(select(TenantNotificationDelivery))).scalars().first() is None


async def test_dispatch_missing_email_address_fails_channel(factory, seeded) -> None:  # noqa: ANN001
    async with factory() as s:
        await _set_path(s)
        event = await _publish(s, recipient_email=None, channels=["email"])
        status = await dispatch_event(s, event)
        await s.commit()
    assert status == "failed"
    async with factory() as s:
        await _set_path(s)
        d = (await s.execute(select(TenantNotificationDelivery))).scalars().one()
    assert d.status == "failed"
    assert "recipient" in (d.error_message or "")


async def test_dispatch_skips_already_sent_channel(factory, seeded) -> None:  # noqa: ANN001
    async with factory() as s:
        await _set_path(s)
        event = await _publish(s, channels=["email"])
        assert await dispatch_event(s, event) == "sent"
        # Second dispatch must not double-send: no new delivery row.
        assert await dispatch_event(s, event) == "sent"
        await s.commit()
    async with factory() as s:
        await _set_path(s)
        rows = list((await s.execute(select(TenantNotificationDelivery))).scalars())
    assert len(rows) == 1
```

- [ ] **Step 2: Run to verify failure** — FAIL (`dispatcher` missing).

- [ ] **Step 3: Write the implementation**

`app/core/notifications/dispatcher.py`:

```python
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
    delivery_model = PlatformNotificationDelivery if is_platform else TenantNotificationDelivery
    preference_model = PlatformNotificationPreference if is_platform else TenantNotificationPreference

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
    attempts = {ch: sum(1 for d in prior if d.channel == ch) for ch in set(d.channel for d in prior)}

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
    provider = get_email_provider() if channel == "email" else get_sms_provider()
    if template is None:
        return _failure(provider.name, "no active template")
    try:
        if channel == "email":
            if not event.recipient_email:
                return _failure(provider.name, "no recipient email")
            external_id = await provider.send(  # type: ignore[call-arg]
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
            external_id = await provider.send(  # type: ignore[call-arg]
                to=event.recipient_phone,
                body=render(template.sms_body or template.body_text or "", event.context, html=False),
            )
    except Exception as exc:  # provider or render failure — never crash the beat
        _log.warning("notification.channel_failed", channel=channel, error=str(exc))
        return _failure(provider.name, str(exc)[:500])
    return {"provider": provider.name, "status": "sent", "external_id": external_id, "error_message": None}


def _failure(provider: str, message: str) -> dict[str, Any]:
    return {"provider": provider, "status": "failed", "external_id": None, "error_message": message}
```

- [ ] **Step 4: Run to verify pass** — `python -m pytest tests/core/notifications/ -q` → all PASS.

- [ ] **Step 5: Lint, typecheck, commit**

```bash
git add app/core/notifications/dispatcher.py tests/core/notifications/test_dispatch.py
git commit -m "feat(notifications): channel dispatcher (preferences, retries-safe, statuses)"
```

---

### Task 6: Beat jobs + Celery registration

**Files:**
- Create: `app/core/notifications/beat.py`
- Modify: `app/workers/celery_app.py`
- Test: `tests/core/notifications/test_dispatch.py` (append)

**Interfaces:**
- Consumes: dispatcher, models.
- Produces three Celery tasks (sync wrappers over async, per `app/modules/fees/beat.py` pattern — `asyncio.run`, fresh engine, `_SCHEMA_RE` guard, iterate `platform` + active tenant schemas):
  - `dispatch_pending_notifications` (beat: 30s) — per schema: `SELECT ... WHERE status='queued' AND scheduled_at <= now() ORDER BY scheduled_at LIMIT 100 FOR UPDATE SKIP LOCKED`, dispatch each, one transaction per schema batch.
  - `retry_failed_notifications` (beat: 300s) — re-queue events in (`partial`,`failed`) whose failed channels all have `attempt < 3` and latest delivery older than 5 minutes: set `status='queued'`, `scheduled_at=now()`. Events with a channel at 3 attempts stay terminal.
  - `purge_old_notification_events` (beat: daily) — delete events with `status != 'queued'` and `created_at < now() - interval '180 days'` (deliveries cascade).
  - A testable async core per task (`_dispatch_for_schema(engine, schema) -> int`, etc.) so tests call the async functions directly without Celery.

- [ ] **Step 1: Write the failing tests**

Append to `test_dispatch.py`:

```python
from app.core.notifications.beat import (  # noqa: E402
    _dispatch_for_schema,
    _purge_for_schema,
    _retry_for_schema,
)


async def test_beat_dispatches_due_queued_events(
    test_engine: AsyncEngine, factory, seeded  # noqa: ANN001
) -> None:
    async with factory() as s:
        await _set_path(s)
        event = await _publish(s)
        await s.commit()
    count = await _dispatch_for_schema(test_engine, SCHEMA)
    assert count == 1
    async with factory() as s:
        await _set_path(s)
        row = await s.get(TenantNotificationEvent, event.id)
    assert row is not None and row.status == "sent"
    # Second run: nothing queued.
    assert await _dispatch_for_schema(test_engine, SCHEMA) == 0


async def test_retry_requeues_failed_under_attempt_cap(
    test_engine: AsyncEngine, factory, seeded  # noqa: ANN001
) -> None:
    async with factory() as s:
        await _set_path(s)
        event = await _publish(s, recipient_email=None, channels=["email"])
        await s.commit()
    await _dispatch_for_schema(test_engine, SCHEMA)  # -> failed (no email addr)
    async with factory() as s:
        await _set_path(s)
        # Age the delivery so backoff allows a retry.
        await s.execute(
            text("UPDATE notification_deliveries SET sent_at = now() - interval '10 minutes'")
        )
        await s.commit()
    requeued = await _retry_for_schema(test_engine, SCHEMA, max_attempts=3)
    assert requeued == 1
    async with factory() as s:
        await _set_path(s)
        row = await s.get(TenantNotificationEvent, event.id)
    assert row is not None and row.status == "queued"


async def test_purge_deletes_only_old_terminal_events(
    test_engine: AsyncEngine, factory, seeded  # noqa: ANN001
) -> None:
    async with factory() as s:
        await _set_path(s)
        old = await _publish(s)
        fresh = await _publish(s)
        await dispatch_event(s, old)
        await dispatch_event(s, fresh)
        await s.flush()
        await s.execute(
            text("UPDATE notification_events SET created_at = now() - interval '200 days' WHERE id = :i"),
            {"i": str(old.id)},
        )
        await s.commit()
    deleted = await _purge_for_schema(test_engine, SCHEMA, days=180)
    assert deleted == 1
    async with factory() as s:
        await _set_path(s)
        assert await s.get(TenantNotificationEvent, old.id) is None
        assert await s.get(TenantNotificationEvent, fresh.id) is not None
```

- [ ] **Step 2: Run to verify failure** — FAIL (`beat` missing).

- [ ] **Step 3: Write the implementation**

`app/core/notifications/beat.py` — follow `app/modules/fees/beat.py` structure:
module-level `_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")`; an
`async def _schemas(engine) -> list[str]` returning `["platform"] + active tenant
schemas` (`SELECT schema_name FROM platform.tenants WHERE is_active = true`,
regex-filtered); the three `_..._for_schema(engine, schema, ...)` async cores; and
three Celery tasks (`@celery_app.task`) each doing
`asyncio.run(_run_all(...))` over a fresh `create_async_engine(get_settings().database_url)`
(match the exact engine-creation idiom used in `fees/beat.py`), disposing the engine
in a `finally`. Core implementations:

```python
async def _dispatch_for_schema(engine: AsyncEngine, schema: str) -> int:
    from app.core.notifications.dispatcher import dispatch_event
    from app.core.notifications.models import (
        PlatformNotificationEvent,
        TenantNotificationEvent,
    )

    model = PlatformNotificationEvent if schema == "platform" else TenantNotificationEvent
    factory = async_sessionmaker(engine, expire_on_commit=False)
    dispatched = 0
    async with factory() as session:
        if schema == "platform":
            session.sync_session.info["is_platform"] = True
        await session.execute(text(f"SET LOCAL search_path TO {schema}, platform"))  # noqa: S608
        events = list(
            (
                await session.execute(
                    select(model)
                    .where(model.status == "queued", model.scheduled_at <= func.now())
                    .order_by(model.scheduled_at)
                    .limit(100)
                    .with_for_update(skip_locked=True)
                )
            ).scalars()
        )
        for event in events:
            await dispatch_event(session, event)
            dispatched += 1
        await session.commit()
    return dispatched
```

`_retry_for_schema(engine, schema, *, max_attempts=3)`: select events in
(`partial`,`failed`); for each, load its deliveries; if every failed channel has
`attempt < max_attempts` and the newest delivery `sent_at < now() - 5 min`, set
`status='queued'`, `scheduled_at=now()`; count and commit.

`_purge_for_schema(engine, schema, *, days=180)`: one `DELETE FROM
notification_events WHERE status != 'queued' AND created_at < now() - make_interval(days => :days)`
via `text()` (per-schema search_path), return rowcount.

In `app/workers/celery_app.py`: add `"app.core.notifications.beat"` to the
`include` list and three `beat_schedule` entries:

```python
        "dispatch-pending-notifications": {
            "task": "app.core.notifications.beat.dispatch_pending_notifications",
            "schedule": 30.0,
        },
        "retry-failed-notifications": {
            "task": "app.core.notifications.beat.retry_failed_notifications",
            "schedule": 300.0,
        },
        "purge-old-notification-events": {
            "task": "app.core.notifications.beat.purge_old_notification_events",
            "schedule": 24 * 3600.0,  # daily
        },
```

- [ ] **Step 4: Run to verify pass** — `python -m pytest tests/core/notifications/ -q` → all PASS.

- [ ] **Step 5: Lint, typecheck, commit**

```bash
git add app/core/notifications/beat.py app/workers/celery_app.py tests/core/notifications/test_dispatch.py
git commit -m "feat(notifications): dispatch/retry/purge beat jobs (SKIP LOCKED claim)"
```

---

### Task 7: HTTP APIs (self ×3 audiences + platform admin) + schemas

**Files:**
- Create: `app/core/notifications/schemas.py`, `app/core/notifications/api.py`
- Modify: `app/main.py`
- Test: `tests/core/notifications/test_api.py` (create)

**Interfaces:**
- Consumes: models, service (resend re-queues directly — status flip allowed ONLY here because resend is an admin re-queue, implemented as `status='queued'; scheduled_at=now()`, still dispatched by the beat), renderer (feed titles/bodies from the in_app template).
- Produces routers (all registered in `app/main.py`):
  - `platform_self_router` — `/platform/notifications/me*`, `CurrentPlatformUser` + `get_platform_session`.
  - `tenant_self_router` — `/notifications/me*`, `CurrentTenantUser` + `get_tenant_session`.
  - `member_self_router` — `/member/notifications/me*`, `CurrentMember` + `get_tenant_session`.
  - Self endpoints (identical shapes): `GET ""` → `list[NotificationFeedItemOut]` (`unread_only: bool = False`, `limit: int = 50 (le=200)`, `offset: int = 0`; only rows where `'in_app' = ANY(channels)`, newest first; `title`/`body` rendered from the in_app template, fallback to the raw code + empty body when no template); `POST "/{event_id}/read"` → 204 (404 unless the row belongs to this recipient kind+id); `GET "/preferences"` → `list[NotificationPreferenceOut]` (only stored rows); `PUT "/preferences"` body `list[NotificationPreferenceIn {event_code, channel, enabled}]` → upsert rows for this user, return the stored list.
  - `platform_admin_router` — `/platform/notifications/*`: `GET /templates` (`CurrentSupport`), `POST /templates` (`CurrentAdmin`, 409 on (code,channel,locale) duplicate), `PATCH /templates/{id}` (`CurrentAdmin`; editable: subject_template, body_html, body_text, sms_body, variables, is_active), `GET /events` (`CurrentSupport`; filters `recipient_user_id`, `event_code`, `status`; platform-schema events only), `POST /events/{id}/resend` (`CurrentAdmin`; 404 unknown, 409 if `queued`; else re-queue).
  - Pydantic in `schemas.py`: `NotificationFeedItemOut {id, event_code, title, body, created_at, read_at, status}`, `NotificationPreferenceIn/Out`, `NotificationTemplateIn/Patch/Out`, `NotificationEventAdminOut` (full row minus context? include context — admins may inspect).
- Route-order note: `member_self_router` paths start `/member/notifications/...` — no collision with other member routers. The platform admin router and platform self router share the `/platform/notifications` prefix; register the **self router first** and keep admin paths (`/templates`, `/events`) distinct from `me` — no `{param}` segments at that level, so order is safe regardless.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/notifications/test_api.py` — stub-auth client fixture like
`tests/modules/credit/test_member_apply_api.py` (lifespan + tenant session
override + cleanup of notification tables and `members`/`tenant_users` rows it
seeds; platform actor header `X-Platform-Actor-ID` with `platform_actor_id`
fixture — copy the actor fixtures used by `tests/platform_/kyc/` tests). Cover:

```python
# Representative test list (write all of these):
# - member feed: seed member; publish 2 events for them (in_app) + 1 for another member;
#   GET /member/notifications/me returns 2 rendered items, newest first; unread_only after
#   marking one read returns 1. Cross-member read POST -> 404.
# - tenant operator feed: publish for tenant_user; GET /notifications/me with
#   X-Tenant-Actor-ID returns it; POST /{id}/read flips read_at (204, then unread_only = []).
# - platform feed: is_platform session; GET /platform/notifications/me.
# - preferences: PUT /notifications/me/preferences [{"event_code": "system_announcement",
#   "channel": "email", "enabled": false}] -> stored; GET returns it; dispatcher test
#   already proves enforcement.
# - admin templates: GET list (support ok); POST duplicate (code,channel,locale) -> 409;
#   PATCH body_text -> reflected in GET.
# - admin events: publish platform event; GET /platform/notifications/events?status=queued
#   finds it; POST /platform/notifications/events/{id}/resend on queued -> 409; after
#   marking it failed via SQL, resend -> 200 and status back to queued.
# - auth: member cannot call /platform/notifications/templates (401/403).
```

Write each as a real test function with full arrange/act/assert — the comment
block above is the coverage checklist, not the deliverable.

- [ ] **Step 2: Run to verify failure** — routes 404.

- [ ] **Step 3: Write the implementation**

`schemas.py` and `api.py` per the Interfaces block. Implementation notes:

- Shared feed query helper:

  ```python
  async def _feed(session, model, kind: str, user_id: uuid.UUID, unread_only: bool, limit: int, offset: int): ...
  ```

  filters `model.recipient_kind == kind, model.recipient_user_id == user_id`,
  `model.channels.any("in_app")` (SQLAlchemy ARRAY `.any()`), `read_at IS NULL`
  when unread_only, `order_by(model.created_at.desc())`.
- Title/body rendering: load the `in_app` template per distinct code once per
  request; `render(subject_template, context, html=False)` / `render(body_text, ...)`;
  fall back to `(event_code, "")` if no template. Render errors → fallback, never 500.
- `POST /{event_id}/read`: fetch by id, verify kind+user match else 404, set
  `read_at = now()` (idempotent — already-read is still 204).
- Preferences PUT: validate `event_code` via catalog and `channel` via `CHANNELS`
  (422 on unknown); upsert by unique key; return stored rows for the user.
- Admin events search runs on the **platform session** (`get_platform_session`);
  tenant-schema events are increment-3 portal territory.
- Resend: set `status="queued"`, `scheduled_at=func.now()` — the beat delivers;
  the existing-sent-channel guard in the dispatcher prevents double sends.
- Register in `app/main.py` (imports + 4 `include_router` lines next to the other
  notification-adjacent routers; member router near the other member routers).

- [ ] **Step 4: Run to verify pass** — `python -m pytest tests/core/notifications/ -q` → all PASS.

- [ ] **Step 5: Lint, typecheck, commit**

```bash
git add app/core/notifications app/main.py tests/core/notifications/test_api.py
git commit -m "feat(notifications): self feed/read/preferences APIs (3 audiences) + platform admin API"
```

---

### Task 8: Close-out — full suites + CLAUDE.md contracts

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Backend suite**

`python -m ruff check app/ tests/ && python -m mypy app/ && python -m pytest tests/core/notifications/ tests/core/ tests/modules/members/ -q`
(run `tests/modules/credit/` separately — known credit↔core suite-order flake). Expected: green.

- [ ] **Step 2: Migration sanity**

`alembic -c alembic/platform/alembic.ini upgrade head --sql | tail -5` and the tenant
equivalent render valid SQL (offline mode) — same smoke previous increments used.
If the repo's alembic invocation differs, use the project's documented command
(`grep alembic Makefile`).

- [ ] **Step 3: Update CLAUDE.md**

Append a new section after "## KYC tracking contracts":

```markdown
## Notifications contracts (Phase 3 increment 1 — do not violate)

- `NotificationService.publish()` (app/core/notifications/service.py) is the ONLY
  path that creates `notification_events` rows. It writes in the CALLER's
  transaction — the event row is the notification outbox; there is no RabbitMQ hop
  for direct publishes. Dispatch happens exclusively via the
  `dispatch_pending_notifications` beat (30s, `FOR UPDATE SKIP LOCKED`).
- Notifications never carry secrets (reset tokens, passwords) or sensitive PII.
  The template `variables` allow-list is enforced at publish time (unknown context
  key → ValueError). The password_reset notification is a NOTICE — the token is
  never in the context.
- Recipient kinds: `platform_user | tenant_user | member`. Templates live in the
  PLATFORM schema only; events/deliveries/preferences exist in both schemas.
- Providers are selected via `notify_email_provider` / `notify_sms_provider`
  settings (`null` default, `log` available). Adding a real provider must not
  change any call site or the dispatcher.
- `in_app` is provider-less: the event row is the feed item (`read_at` marks it
  read) and it writes NO delivery row. The dispatcher/beat is the only code that
  flips event `status` (the admin resend endpoint re-queues; it never marks sent);
  the self API touches only `read_at` and preferences.
- Preferences default to enabled (absence of a row = enabled) and are enforced at
  dispatch, never at publish. Retries cap at 3 attempts per channel; a channel
  with a `sent` delivery is never re-sent.
- Self API paths per audience: `/platform/notifications/me*`, `/notifications/me*`,
  `/member/notifications/me*`. Cross-recipient access → 404. Increment 2 wires the
  13 call sites; increment 3 builds the portal surfaces — until then the catalog
  exists but nothing publishes in production code paths.
```

Also update the Phase-3 row in the roadmap status table ("Not started" → "In progress — increment 1").

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): notifications framework contracts (Phase 3 increment 1)"
```

---

## Out of scope for this plan

- Wiring any call site (increment 2), including the `member_activated` outbox consumer.
- Portal surfaces: bell feed, preferences UI, admin template/event screens, provider banner (increment 3).
- Real providers, bulk system_announcement, template versioning, locales, digests,
  rate limiting beyond `dedupe_key` (spec: v2).
