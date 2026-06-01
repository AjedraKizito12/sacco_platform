from __future__ import annotations

import uuid
from datetime import date, datetime  # noqa: TC003
from decimal import Decimal
from typing import Any

from sqlalchemy import (
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
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit.mixin import AuditableMixin
from app.core.db import Base


class SubscriptionPlan(AuditableMixin, Base):
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
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
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
        UUID(as_uuid=True),
        ForeignKey("platform.tenants.id", name="fk_subscriptions_tenant"),
        nullable=False,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.subscription_plans.id", name="fk_subscriptions_plan"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="trialing")
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    current_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    current_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    grace_period_ends_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_billing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
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
        UUID(as_uuid=True),
        ForeignKey("platform.tenants.id", name="fk_invoices_tenant"),
        nullable=False,
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
    issued_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    due_at: Mapped[date] = mapped_column(Date, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    voided_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
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
        UUID(as_uuid=True),
        ForeignKey("platform.invoices.id", name="fk_payments_invoice"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="UGX")
    payment_method: Mapped[str] = mapped_column(Text, nullable=False)
    external_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "platform.platform_users.id", name="fk_payments_recorded_by"
        ),
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "platform.approval_requests.id", name="fk_payments_approval"
        ),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    confirmed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
