from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import TIMESTAMP, Boolean, Date, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit.mixin import AuditableMixin
from app.core.db import Base


class OrganizationProfile(AuditableMixin, Base):
    """Singleton SACCO organization KYC profile (one row per tenant schema).

    Self-attested by the tenant admin. ``verified`` is platform-controlled and
    reset to false whenever a catalog value materially changes.
    """

    __tablename__ = "organization_profile"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    legal_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    registration_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    registered_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_contact_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_contact_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    registration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    regulator_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_contact_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    postal_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    district_region: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(Text, nullable=True)

    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false", default=False)
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    verified_by_platform_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Singleton guard: constant value + unique constraint → at most one row.
    singleton: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true", default=True)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("singleton", name="uq_organization_profile_singleton"),
    )
