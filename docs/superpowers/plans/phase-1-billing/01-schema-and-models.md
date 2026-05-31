# Phase 1 Sub-Plan 01: Schema, Models, Schemas

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** Cut `feat/phase-1-billing/01-schema` from `feat/phase-1-billing` before starting.

**Goal:** Land the entire billing data layer in one sub-plan: Alembic migration 006 with 5 new platform tables + an ALTER on `platform.tenants`, the SQLAlchemy models, the Pydantic schemas, and the conftest registration so the test DB picks the tables up. Tests assert each model registers, inserts, and round-trips correctly.

**Architecture:** Every table lives in the `platform` schema (`__table_args__ = {"schema": "platform"}`). The `subscription_status` column on `platform.tenants` is the runtime gate (Sub-Plan 04 wires the middleware that reads it). Monetary values use `Numeric(19, 4)`. The `currency` columns are declared but UGX-only in v1.

**Tech Stack:** SQLAlchemy 2.0 async, Alembic, Pydantic v2.

**Roadmap reference:** `docs/superpowers/plans/saas-launch-roadmap.md` §5 Phase 1.

**Prerequisite:** None — first sub-plan in Phase 1. The integration branch `feat/phase-1-billing` exists.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `alembic/platform/versions/006_billing_tables.py` | Create | Alembic migration: 5 new tables + tenants ALTER |
| `app/platform_/billing/__init__.py` | Create | Empty package marker |
| `app/platform_/billing/models.py` | Create | 5 SQLAlchemy models (no audit mixin on `invoices`/`payments`/`invoice_line_items` — see Task 2 §2.4) |
| `app/platform_/billing/schemas.py` | Create | Pydantic response/request types |
| `app/platform_/billing/services/__init__.py` | Create | Empty marker (service code lands in SP02–03) |
| `app/platform_/billing/processors/__init__.py` | Create | Empty marker (processor code lands in SP02) |
| `tests/platform_/billing/__init__.py` | Create | Empty marker |
| `tests/platform_/billing/test_models.py` | Create | Model round-trip + constraint tests |
| `tests/conftest.py` | Modify | Register billing models in the `test_engine` fixture |

---

## Task 1: Alembic migration

**Files:**
- Create: `alembic/platform/versions/006_billing_tables.py`

- [ ] **Step 1: Write the migration**

```python
# alembic/platform/versions/006_billing_tables.py
"""Phase 1 Billing module — 5 platform tables + tenants ALTER.

Revision: 006
Depends on: 005
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── subscription_plans ─────────────────────────────────────────────────────
    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=False, server_default="UGX"),
        sa.Column("base_price", sa.Numeric(19, 4), nullable=False),
        sa.Column("per_user_price", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("per_member_price", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("billing_period", sa.Text(), nullable=False),
        sa.Column("member_limit", sa.Integer(), nullable=True),
        sa.Column("user_limit", sa.Integer(), nullable=True),
        sa.Column(
            "features",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("trial_period_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("grace_period_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "billing_period IN ('monthly', 'quarterly', 'annual')",
            name="ck_sub_plans_billing_period",
        ),
        sa.UniqueConstraint("code", name="uq_sub_plans_code"),
        schema="platform",
    )
    op.create_index(
        "ix_sub_plans_is_active", "subscription_plans", ["is_active"], schema="platform",
    )

    # ── subscriptions ──────────────────────────────────────────────────────────
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("plan_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("current_period_start", sa.Date(), nullable=False),
        sa.Column("current_period_end", sa.Date(), nullable=False),
        sa.Column("grace_period_ends_at", sa.Date(), nullable=True),
        sa.Column("cancelled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("next_billing_date", sa.Date(), nullable=True),
        sa.Column(
            "metadata_json",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["platform.tenants.id"], name="fk_subscriptions_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["platform.subscription_plans.id"], name="fk_subscriptions_plan",
        ),
        sa.CheckConstraint(
            "status IN ('trialing', 'active', 'past_due', 'suspended', 'cancelled')",
            name="ck_subscriptions_status",
        ),
        schema="platform",
    )
    op.create_index(
        "ix_subscriptions_tenant_status",
        "subscriptions",
        ["tenant_id", "status"],
        schema="platform",
    )
    op.create_index(
        "ix_subscriptions_period_end",
        "subscriptions",
        ["current_period_end"],
        schema="platform",
        postgresql_where=sa.text("status IN ('trialing', 'active', 'past_due')"),
    )
    # One *live* subscription per tenant. Cancelled rows accumulate without limit.
    op.create_index(
        "uq_subscriptions_live_tenant",
        "subscriptions",
        ["tenant_id"],
        unique=True,
        schema="platform",
        postgresql_where=sa.text("status IN ('trialing', 'active', 'past_due')"),
    )

    # ── invoices ───────────────────────────────────────────────────────────────
    op.create_table(
        "invoices",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("invoice_number", sa.Text(), nullable=False),
        sa.Column("subscription_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("billing_period_start", sa.Date(), nullable=False),
        sa.Column("billing_period_end", sa.Date(), nullable=False),
        sa.Column("amount_subtotal", sa.Numeric(19, 4), nullable=False),
        sa.Column("amount_tax", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("amount_total", sa.Numeric(19, 4), nullable=False),
        sa.Column("amount_paid", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("currency", sa.Text(), nullable=False, server_default="UGX"),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("issued_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("due_at", sa.Date(), nullable=False),
        sa.Column("paid_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("voided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("pdf_storage_key", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["platform.subscriptions.id"], name="fk_invoices_subscription",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["platform.tenants.id"], name="fk_invoices_tenant",
        ),
        sa.UniqueConstraint("invoice_number", name="uq_invoices_number"),
        sa.CheckConstraint(
            "status IN ('draft', 'issued', 'partial', 'paid', 'overdue', 'void')",
            name="ck_invoices_status",
        ),
        schema="platform",
    )
    op.create_index(
        "ix_invoices_tenant_status",
        "invoices",
        ["tenant_id", "status"],
        schema="platform",
    )
    op.create_index(
        "ix_invoices_due",
        "invoices",
        ["due_at"],
        schema="platform",
        postgresql_where=sa.text("status IN ('issued', 'partial', 'overdue')"),
    )

    # ── invoice_line_items ─────────────────────────────────────────────────────
    op.create_table(
        "invoice_line_items",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("invoice_id", sa.UUID(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(19, 4), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("line_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["platform.invoices.id"],
            ondelete="CASCADE",
            name="fk_invoice_line_items_invoice",
        ),
        schema="platform",
    )
    op.create_index(
        "ix_invoice_line_items_invoice",
        "invoice_line_items",
        ["invoice_id"],
        schema="platform",
    )

    # ── payments ───────────────────────────────────────────────────────────────
    op.create_table(
        "payments",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("invoice_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default="UGX"),
        sa.Column("payment_method", sa.Text(), nullable=False),
        sa.Column("external_reference", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.UUID(), nullable=False),
        sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("approval_request_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("confirmed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["invoice_id"], ["platform.invoices.id"], name="fk_payments_invoice",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"],
            ["platform.platform_users.id"],
            name="fk_payments_recorded_by",
        ),
        sa.ForeignKeyConstraint(
            ["approval_request_id"],
            ["platform.approval_requests.id"],
            name="fk_payments_approval",
        ),
        sa.CheckConstraint(
            "payment_method IN ('bank_transfer', 'mobile_money', 'cash', 'cheque')",
            name="ck_payments_payment_method",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'rejected')",
            name="ck_payments_status",
        ),
        schema="platform",
    )
    op.create_index(
        "ix_payments_invoice", "payments", ["invoice_id"], schema="platform",
    )

    # ── ALTER platform.tenants ─────────────────────────────────────────────────
    op.add_column(
        "tenants",
        sa.Column(
            "subscription_status",
            sa.Text(),
            nullable=False,
            server_default="pending",
        ),
        schema="platform",
    )
    op.add_column(
        "tenants",
        sa.Column("current_subscription_id", sa.UUID(), nullable=True),
        schema="platform",
    )
    op.create_foreign_key(
        "fk_tenants_current_subscription",
        "tenants",
        "subscriptions",
        ["current_subscription_id"],
        ["id"],
        source_schema="platform",
        referent_schema="platform",
    )
    op.create_check_constraint(
        "ck_tenants_subscription_status",
        "tenants",
        "subscription_status IN ('pending', 'trialing', 'active', 'past_due', 'suspended', 'cancelled')",
        schema="platform",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_tenants_current_subscription",
        "tenants",
        type_="foreignkey",
        schema="platform",
    )
    op.drop_constraint(
        "ck_tenants_subscription_status", "tenants", type_="check", schema="platform",
    )
    op.drop_column("tenants", "current_subscription_id", schema="platform")
    op.drop_column("tenants", "subscription_status", schema="platform")
    op.drop_table("payments", schema="platform")
    op.drop_table("invoice_line_items", schema="platform")
    op.drop_table("invoices", schema="platform")
    op.drop_table("subscriptions", schema="platform")
    op.drop_table("subscription_plans", schema="platform")
```

- [ ] **Step 2: Smoke-check the file parses**

```bash
python -c "import ast; ast.parse(open('alembic/platform/versions/006_billing_tables.py').read()); print('parsed OK')"
```

Expected: `parsed OK`.

- [ ] **Step 3: Commit**

```bash
git add alembic/platform/versions/006_billing_tables.py
git commit -m "feat(billing): Alembic migration 006 — 5 platform billing tables + tenants ALTER"
```

---

## Task 2: SQLAlchemy models

**Files:**
- Create: `app/platform_/billing/__init__.py` (empty)
- Create: `app/platform_/billing/services/__init__.py` (empty)
- Create: `app/platform_/billing/processors/__init__.py` (empty)
- Create: `app/platform_/billing/models.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Create package markers**

```bash
mkdir -p app/platform_/billing/services app/platform_/billing/processors tests/platform_/billing
touch app/platform_/billing/__init__.py
touch app/platform_/billing/services/__init__.py
touch app/platform_/billing/processors/__init__.py
touch tests/platform_/billing/__init__.py
```

- [ ] **Step 2: Write `app/platform_/billing/models.py`**

```python
# app/platform_/billing/models.py
"""SQLAlchemy models for the billing module.

All tables live in the `platform` schema. Money is `Numeric(19, 4)`.
UGX-only in v1; the `currency` columns exist for forward compatibility.

Audit policy:
    - SubscriptionPlan, Subscription: AuditableMixin
        (operator edits to plans / lifecycle changes must be traceable).
    - Invoice, InvoiceLineItem, Payment: NO AuditableMixin
        (these are append-only / state-machine rows; their lifecycle is
        captured by status transitions and dedicated audit events the
        service layer writes via `_write_audit_event`. See SP03.)

State machines:
    Subscription.status:
        pending → trialing → active → past_due → suspended → cancelled
                          ↑___________↓
        See SP02 SubscriptionService for the transition helpers.

    Invoice.status:
        draft → issued → (partial | paid | overdue | void)
        See SP03 InvoiceService.

    Payment.status:
        pending → (confirmed | rejected)
        Confirmed payments mutate the parent Invoice.amount_paid in the same
        DB transaction. See SP03 PaymentService.
"""
from __future__ import annotations

import uuid  # noqa: TC003 — used at runtime by SQLAlchemy
from datetime import date, datetime  # noqa: TC003
from decimal import Decimal  # noqa: TC003
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit.mixin import AuditableMixin
from app.core.db import Base


class SubscriptionPlan(AuditableMixin, Base):
    """Configurable subscription plan. Operators CRUD via the admin API."""

    __tablename__ = "subscription_plans"
    __table_args__ = (
        UniqueConstraint("code", name="uq_sub_plans_code"),
        CheckConstraint(
            "billing_period IN ('monthly', 'quarterly', 'annual')",
            name="ck_sub_plans_billing_period",
        ),
        Index("ix_sub_plans_is_active", "is_active"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="UGX")
    base_price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    per_user_price: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), nullable=False, default=Decimal("0")
    )
    per_member_price: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), nullable=False, default=Decimal("0")
    )
    billing_period: Mapped[str] = mapped_column(Text, nullable=False)
    member_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    features: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"),
    )
    trial_period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    grace_period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Subscription(AuditableMixin, Base):
    """One tenant's current (or historical) subscription to a plan."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('trialing', 'active', 'past_due', 'suspended', 'cancelled')",
            name="ck_subscriptions_status",
        ),
        Index("ix_subscriptions_tenant_status", "tenant_id", "status"),
        Index(
            "ix_subscriptions_period_end",
            "current_period_end",
            postgresql_where=text("status IN ('trialing', 'active', 'past_due')"),
        ),
        Index(
            "uq_subscriptions_live_tenant",
            "tenant_id",
            unique=True,
            postgresql_where=text("status IN ('trialing', 'active', 'past_due')"),
        ),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform.tenants.id", name="fk_subscriptions_tenant"), nullable=False
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.subscription_plans.id", name="fk_subscriptions_plan"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    current_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    current_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    grace_period_ends_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_billing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # The DDL calls this `metadata`, but `metadata` is reserved by SQLAlchemy's
    # declarative system. The column maps to `metadata_json` in Python.
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata_json",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Invoice(Base):
    """One billing-period invoice. Mostly append-only after `issued`."""

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("invoice_number", name="uq_invoices_number"),
        CheckConstraint(
            "status IN ('draft', 'issued', 'partial', 'paid', 'overdue', 'void')",
            name="ck_invoices_status",
        ),
        Index("ix_invoices_tenant_status", "tenant_id", "status"),
        Index(
            "ix_invoices_due",
            "due_at",
            postgresql_where=text("status IN ('issued', 'partial', 'overdue')"),
        ),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invoice_number: Mapped[str] = mapped_column(Text, nullable=False)
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.subscriptions.id", name="fk_invoices_subscription"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform.tenants.id", name="fk_invoices_tenant"), nullable=False
    )
    billing_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    billing_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    amount_subtotal: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    amount_tax: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), nullable=False, default=Decimal("0")
    )
    amount_total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="UGX")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    issued_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    due_at: Mapped[date] = mapped_column(Date, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class InvoiceLineItem(Base):
    """One line on an invoice: 'Base subscription', 'Per-user (12 × UGX 5000)', etc."""

    __tablename__ = "invoice_line_items"
    __table_args__ = (
        Index("ix_invoice_line_items_invoice", "invoice_id"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "platform.invoices.id",
            ondelete="CASCADE",
            name="fk_invoice_line_items_invoice",
        ),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    line_order: Mapped[int] = mapped_column(Integer, nullable=False)


class Payment(Base):
    """A recorded payment against an invoice. Recorded by an operator (maker);
    confirmed by a second operator (checker) via the maker-checker flow.
    """

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            "payment_method IN ('bank_transfer', 'mobile_money', 'cash', 'cheque')",
            name="ck_payments_payment_method",
        ),
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'rejected')",
            name="ck_payments_status",
        ),
        Index("ix_payments_invoice", "invoice_id"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform.invoices.id", name="fk_payments_invoice"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="UGX")
    payment_method: Mapped[str] = mapped_column(Text, nullable=False)
    external_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.platform_users.id", name="fk_payments_recorded_by"),
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "platform.approval_requests.id", name="fk_payments_approval",
        ),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    confirmed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
```

- [ ] **Step 3: Register the models in `tests/conftest.py`**

Open `tests/conftest.py`. Inside the `test_engine` fixture, locate the block of `import app.modules.*.models` and `import app.platform_.models` lines. Add this import to the same block:

```python
    import app.platform_.billing.models  # noqa: F401 — registers billing tables in Base.metadata
```

The exact placement: immediately after `import app.platform_.models` (alphabetic/topical order — billing is a sub-package of platform_).

- [ ] **Step 4: Run the test-engine collection smoke**

```bash
env -u DATABASE_URL pytest tests/test_main.py -q
```

Expected: tests pass (the test-engine fixture now also creates the 5 billing tables — but no existing test depends on them yet, so they're just dormant).

- [ ] **Step 5: Commit**

```bash
git add app/platform_/billing/__init__.py app/platform_/billing/models.py \
        app/platform_/billing/services/__init__.py \
        app/platform_/billing/processors/__init__.py \
        tests/platform_/billing/__init__.py \
        tests/conftest.py
git commit -m "feat(billing): SQLAlchemy models — 5 platform billing tables registered"
```

---

## Task 3: Pydantic schemas

**Files:**
- Create: `app/platform_/billing/schemas.py`

- [ ] **Step 1: Write `app/platform_/billing/schemas.py`**

```python
# app/platform_/billing/schemas.py
"""Pydantic request/response schemas for the billing module."""
from __future__ import annotations

import uuid  # noqa: TC003
from datetime import date, datetime  # noqa: TC003
from decimal import Decimal  # noqa: TC003
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ── SubscriptionPlan ───────────────────────────────────────────────────────────


class SubscriptionPlanIn(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    name: str
    description: str | None = None
    currency: str = "UGX"
    base_price: Decimal = Field(..., ge=Decimal("0"))
    per_user_price: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    per_member_price: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    billing_period: str = Field(..., pattern="^(monthly|quarterly|annual)$")
    member_limit: int | None = Field(default=None, ge=0)
    user_limit: int | None = Field(default=None, ge=0)
    features: dict[str, Any] = Field(default_factory=dict)
    trial_period_days: int = Field(default=0, ge=0)
    grace_period_days: int = Field(default=30, ge=0)
    is_active: bool = True


class SubscriptionPlanPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    base_price: Decimal | None = Field(default=None, ge=Decimal("0"))
    per_user_price: Decimal | None = Field(default=None, ge=Decimal("0"))
    per_member_price: Decimal | None = Field(default=None, ge=Decimal("0"))
    member_limit: int | None = Field(default=None, ge=0)
    user_limit: int | None = Field(default=None, ge=0)
    features: dict[str, Any] | None = None
    trial_period_days: int | None = Field(default=None, ge=0)
    grace_period_days: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class SubscriptionPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    description: str | None
    currency: str
    base_price: Decimal
    per_user_price: Decimal
    per_member_price: Decimal
    billing_period: str
    member_limit: int | None
    user_limit: int | None
    features: dict[str, Any]
    trial_period_days: int
    grace_period_days: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ── Subscription ───────────────────────────────────────────────────────────────


class SubscriptionCreateIn(BaseModel):
    tenant_id: uuid.UUID
    plan_id: uuid.UUID
    # Optional override of the start date; defaults to today in the service.
    start_date: date | None = None


class SubscriptionCancelIn(BaseModel):
    reason: str = Field(..., min_length=2)
    # When operator explicitly wants the cancellation to take effect at
    # period end vs immediately. Default = end-of-period (graceful).
    cancel_at_period_end: bool = True


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    plan_id: uuid.UUID
    status: str
    started_at: datetime
    current_period_start: date
    current_period_end: date
    grace_period_ends_at: date | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    next_billing_date: date | None
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


# ── Invoice ────────────────────────────────────────────────────────────────────


class InvoiceLineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    description: str
    quantity: int
    unit_price: Decimal
    amount: Decimal
    line_order: int


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str
    subscription_id: uuid.UUID
    tenant_id: uuid.UUID
    billing_period_start: date
    billing_period_end: date
    amount_subtotal: Decimal
    amount_tax: Decimal
    amount_total: Decimal
    amount_paid: Decimal
    currency: str
    status: str
    issued_at: datetime | None
    due_at: date
    paid_at: datetime | None
    voided_at: datetime | None
    void_reason: str | None
    created_at: datetime
    updated_at: datetime


class InvoiceDetailOut(InvoiceOut):
    line_items: list[InvoiceLineItemOut]


class InvoiceVoidIn(BaseModel):
    reason: str = Field(..., min_length=2)


# ── Payment ────────────────────────────────────────────────────────────────────


class PaymentRecordIn(BaseModel):
    amount: Decimal = Field(..., gt=Decimal("0"))
    currency: str = "UGX"
    payment_method: str = Field(..., pattern="^(bank_transfer|mobile_money|cash|cheque)$")
    external_reference: str | None = None
    notes: str | None = None
    idempotency_key: str = Field(..., min_length=8)


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_id: uuid.UUID
    amount: Decimal
    currency: str
    payment_method: str
    external_reference: str | None
    notes: str | None
    recorded_by: uuid.UUID
    recorded_at: datetime
    approval_request_id: uuid.UUID | None
    status: str
    confirmed_at: datetime | None
```

- [ ] **Step 2: Verify schemas import cleanly**

```bash
env -u DATABASE_URL python -c "from app.platform_.billing.schemas import (
    SubscriptionPlanIn, SubscriptionPlanPatch, SubscriptionPlanOut,
    SubscriptionCreateIn, SubscriptionCancelIn, SubscriptionOut,
    InvoiceLineItemOut, InvoiceOut, InvoiceDetailOut, InvoiceVoidIn,
    PaymentRecordIn, PaymentOut,
); print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add app/platform_/billing/schemas.py
git commit -m "feat(billing): Pydantic schemas for plans, subscriptions, invoices, payments"
```

---

## Task 4: Model round-trip tests

**Files:**
- Create: `tests/platform_/billing/test_models.py`

- [ ] **Step 1: Write the tests**

```python
# tests/platform_/billing/test_models.py
"""Models smoke + round-trip tests for the billing module."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform_.billing.models import (
    Invoice,
    InvoiceLineItem,
    Payment,
    Subscription,
    SubscriptionPlan,
)


@pytest.fixture
async def seeded_plan(platform_session: AsyncSession) -> SubscriptionPlan:
    plan = SubscriptionPlan(
        code=f"plan-{uuid.uuid4().hex[:8]}",
        name="Test Plan",
        base_price=Decimal("50000.0000"),
        per_user_price=Decimal("0"),
        per_member_price=Decimal("0"),
        billing_period="monthly",
    )
    platform_session.add(plan)
    await platform_session.flush()
    return plan


@pytest.fixture
async def seeded_tenant(platform_session: AsyncSession):
    """Seed a minimal Tenant row that subscription/invoice FKs can point at."""
    from app.platform_.models import Tenant

    tenant = Tenant(
        slug=f"t-{uuid.uuid4().hex[:8]}",
        schema_name=f"tenant_t_{uuid.uuid4().hex[:8]}",
        name="Test Tenant",
        is_active=True,
    )
    platform_session.add(tenant)
    await platform_session.flush()
    return tenant


@pytest.fixture
async def seeded_platform_user(platform_session: AsyncSession):
    """Seed a platform_users row for payment FK."""
    from app.platform_.models import PlatformUser

    user = PlatformUser(
        email=f"u-{uuid.uuid4().hex[:8]}@test.example",
        full_name="Test Operator",
        is_active=True,
        is_superuser=True,
    )
    platform_session.add(user)
    await platform_session.flush()
    return user


@pytest.mark.anyio
async def test_subscription_plan_roundtrip(platform_session: AsyncSession, seeded_plan):
    fetched = await platform_session.scalar(
        select(SubscriptionPlan).where(SubscriptionPlan.id == seeded_plan.id)
    )
    assert fetched is not None
    assert fetched.code == seeded_plan.code
    assert fetched.billing_period == "monthly"
    assert fetched.is_active is True
    assert fetched.currency == "UGX"


@pytest.mark.anyio
async def test_subscription_plan_invalid_period_rejected(platform_session: AsyncSession):
    plan = SubscriptionPlan(
        code=f"bad-{uuid.uuid4().hex[:8]}",
        name="Bad",
        base_price=Decimal("1000"),
        billing_period="bogus",  # not in CHECK
    )
    platform_session.add(plan)
    with pytest.raises(IntegrityError):
        await platform_session.flush()


@pytest.mark.anyio
async def test_subscription_roundtrip(
    platform_session: AsyncSession, seeded_plan, seeded_tenant,
):
    sub = Subscription(
        tenant_id=seeded_tenant.id,
        plan_id=seeded_plan.id,
        status="active",
        current_period_start=date(2026, 6, 1),
        current_period_end=date(2026, 6, 30),
    )
    platform_session.add(sub)
    await platform_session.flush()

    fetched = await platform_session.scalar(
        select(Subscription).where(Subscription.id == sub.id)
    )
    assert fetched is not None
    assert fetched.status == "active"
    assert fetched.metadata_json == {}


@pytest.mark.anyio
async def test_subscription_invalid_status_rejected(
    platform_session: AsyncSession, seeded_plan, seeded_tenant,
):
    sub = Subscription(
        tenant_id=seeded_tenant.id,
        plan_id=seeded_plan.id,
        status="not-a-status",
        current_period_start=date(2026, 6, 1),
        current_period_end=date(2026, 6, 30),
    )
    platform_session.add(sub)
    with pytest.raises(IntegrityError):
        await platform_session.flush()


@pytest.mark.anyio
async def test_subscription_one_live_per_tenant(
    platform_session: AsyncSession, seeded_plan, seeded_tenant,
):
    """The partial unique index forbids two non-cancelled subscriptions for the same tenant."""
    sub1 = Subscription(
        tenant_id=seeded_tenant.id,
        plan_id=seeded_plan.id,
        status="active",
        current_period_start=date(2026, 6, 1),
        current_period_end=date(2026, 6, 30),
    )
    platform_session.add(sub1)
    await platform_session.flush()

    sub2 = Subscription(
        tenant_id=seeded_tenant.id,
        plan_id=seeded_plan.id,
        status="active",
        current_period_start=date(2026, 7, 1),
        current_period_end=date(2026, 7, 31),
    )
    platform_session.add(sub2)
    with pytest.raises(IntegrityError):
        await platform_session.flush()


@pytest.mark.anyio
async def test_subscription_cancelled_then_new_active_allowed(
    platform_session: AsyncSession, seeded_plan, seeded_tenant,
):
    """Cancelled subscriptions don't block a fresh active one."""
    sub1 = Subscription(
        tenant_id=seeded_tenant.id,
        plan_id=seeded_plan.id,
        status="cancelled",
        current_period_start=date(2026, 6, 1),
        current_period_end=date(2026, 6, 30),
        cancelled_at=datetime.now(UTC),
    )
    platform_session.add(sub1)
    await platform_session.flush()

    sub2 = Subscription(
        tenant_id=seeded_tenant.id,
        plan_id=seeded_plan.id,
        status="active",
        current_period_start=date(2026, 7, 1),
        current_period_end=date(2026, 7, 31),
    )
    platform_session.add(sub2)
    await platform_session.flush()  # should not raise


@pytest.mark.anyio
async def test_invoice_with_line_items_cascade_delete(
    platform_session: AsyncSession, seeded_plan, seeded_tenant,
):
    sub = Subscription(
        tenant_id=seeded_tenant.id,
        plan_id=seeded_plan.id,
        status="active",
        current_period_start=date(2026, 6, 1),
        current_period_end=date(2026, 6, 30),
    )
    platform_session.add(sub)
    await platform_session.flush()

    invoice = Invoice(
        invoice_number=f"INV-TEST-{uuid.uuid4().hex[:8]}",
        subscription_id=sub.id,
        tenant_id=seeded_tenant.id,
        billing_period_start=date(2026, 6, 1),
        billing_period_end=date(2026, 6, 30),
        amount_subtotal=Decimal("50000.0000"),
        amount_total=Decimal("50000.0000"),
        due_at=date(2026, 7, 7),
    )
    platform_session.add(invoice)
    await platform_session.flush()

    line = InvoiceLineItem(
        invoice_id=invoice.id,
        description="Base subscription",
        quantity=1,
        unit_price=Decimal("50000.0000"),
        amount=Decimal("50000.0000"),
        line_order=1,
    )
    platform_session.add(line)
    await platform_session.flush()

    # Delete the invoice; the line item should cascade.
    await platform_session.delete(invoice)
    await platform_session.flush()

    remaining = await platform_session.scalar(
        select(InvoiceLineItem).where(InvoiceLineItem.id == line.id)
    )
    assert remaining is None


@pytest.mark.anyio
async def test_payment_invalid_method_rejected(
    platform_session: AsyncSession,
    seeded_plan,
    seeded_tenant,
    seeded_platform_user,
):
    sub = Subscription(
        tenant_id=seeded_tenant.id,
        plan_id=seeded_plan.id,
        status="active",
        current_period_start=date(2026, 6, 1),
        current_period_end=date(2026, 6, 30),
    )
    platform_session.add(sub)
    await platform_session.flush()

    invoice = Invoice(
        invoice_number=f"INV-PMT-{uuid.uuid4().hex[:8]}",
        subscription_id=sub.id,
        tenant_id=seeded_tenant.id,
        billing_period_start=date(2026, 6, 1),
        billing_period_end=date(2026, 6, 30),
        amount_subtotal=Decimal("50000"),
        amount_total=Decimal("50000"),
        due_at=date(2026, 7, 7),
        status="issued",
    )
    platform_session.add(invoice)
    await platform_session.flush()

    pmt = Payment(
        invoice_id=invoice.id,
        amount=Decimal("50000"),
        payment_method="paypal",  # not in CHECK
        recorded_by=seeded_platform_user.id,
    )
    platform_session.add(pmt)
    with pytest.raises(IntegrityError):
        await platform_session.flush()


@pytest.mark.anyio
async def test_tenant_subscription_status_check_constraint(
    platform_session: AsyncSession,
):
    """The ALTER on platform.tenants restricts subscription_status values."""
    from app.platform_.models import Tenant
    from sqlalchemy import text as sql_text

    # Insert a tenant with a valid status (default 'pending').
    t = Tenant(
        slug=f"sg-{uuid.uuid4().hex[:8]}",
        schema_name=f"tenant_sg_{uuid.uuid4().hex[:8]}",
        name="Status Gate Tenant",
        is_active=True,
    )
    platform_session.add(t)
    await platform_session.flush()

    # Try to UPDATE to a bogus value — should be rejected.
    with pytest.raises(IntegrityError):
        await platform_session.execute(
            sql_text(
                "UPDATE platform.tenants SET subscription_status = 'bogus' WHERE id = :id"
            ),
            {"id": str(t.id)},
        )
        await platform_session.flush()
```

- [ ] **Step 2: Run the tests**

```bash
env -u DATABASE_URL pytest tests/platform_/billing/test_models.py -v 2>&1 | tail -20
```

Expected: all tests pass.

If any test fails because `Tenant` is missing required columns, inspect
`app/platform_/models.py` and update the `seeded_tenant` fixture in
this test file to include them. Do NOT modify the production model.

- [ ] **Step 3: Run the full suite to confirm no regressions**

```bash
env -u DATABASE_URL pytest tests/ -q --tb=no 2>&1 | tail -5
```

Expected: all 594 existing tests + the new ones pass.

- [ ] **Step 4: Commit**

```bash
git add tests/platform_/billing/test_models.py
git commit -m "test(billing): model round-trip + constraint tests"
```

---

## Task 5: PR back into the integration branch

- [ ] **Step 1: Push the sub-plan branch**

```bash
git push -u origin feat/phase-1-billing/01-schema
```

- [ ] **Step 2: Open the PR**

```bash
gh pr create \
    --base feat/phase-1-billing \
    --head feat/phase-1-billing/01-schema \
    --title "Phase 1 SP01 — Schema, models, schemas" \
    --body "$(cat <<'EOF'
Implements Phase 1 Sub-Plan 01 per
`docs/superpowers/plans/phase-1-billing/01-schema-and-models.md`.

## What's in this PR
- Alembic migration 006 (5 platform tables + tenants ALTER).
- SQLAlchemy models for SubscriptionPlan, Subscription, Invoice,
  InvoiceLineItem, Payment.
- Pydantic schemas (request/response).
- Model round-trip + constraint tests.
- conftest registers the new tables in the test engine.

## Test plan
- [ ] `pytest tests/platform_/billing/test_models.py -v` — all green
- [ ] `pytest tests/ -q` — full suite green (no regressions)
- [ ] `mypy app/platform_/billing/` — clean
- [ ] `ruff check app/platform_/billing/ tests/platform_/billing/` — clean
- [ ] Manual: `alembic upgrade head` on a fresh dev DB succeeds
- [ ] Manual: `alembic downgrade -1` reverses cleanly

## Notes
- Models for Invoice/InvoiceLineItem/Payment intentionally do NOT use
  AuditableMixin. Their lifecycle is captured by status transitions plus
  the service-layer audit events that SP03 introduces.
- The partial unique index on Subscriptions (`uq_subscriptions_live_tenant`)
  enforces one live subscription per tenant at the DB level; cancelled
  subscriptions accumulate.
EOF
)"
```

---

## Self-Review Checklist

- [x] Migration revision matches the next free platform revision (006 after 005).
- [x] Every monetary column is `Numeric(19, 4)`.
- [x] Every CHECK constraint has an explicit name (`ck_*`).
- [x] Every FK has an explicit name (`fk_*`).
- [x] Every index has an explicit name (`ix_*` / `uq_*`).
- [x] No model touches the `metadata` attribute directly — `Subscription.metadata_json` maps to the `metadata_json` column.
- [x] Audit policy explicit: Plans + Subscriptions use AuditableMixin; Invoices / Line items / Payments do not (with the rationale documented in the module docstring).
- [x] Partial unique index enforces one-live-subscription-per-tenant.
- [x] Conftest registers the models so test DB picks them up.
- [x] No code in this sub-plan calls any service or processor — those land in SP02–05.
