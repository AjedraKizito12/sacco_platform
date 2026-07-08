from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit.mixin import AuditableMixin
from app.core.db import Base


class Member(AuditableMixin, Base):
    """One row per SACCO member.

    member_number is set by MemberService from member_number_seq (M-00001 format).
    status starts as 'pending'; transitions require maker-checker approval.
    joined_at is set to the activation date when status first becomes 'active'.
    All columns are in the tenant schema — no schema= in __table_args__.
    """

    __tablename__ = "members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    member_number: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    gender: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    physical_address: Mapped[str | None] = mapped_column(Text, nullable=True)

    # KYC fields
    national_id_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    id_document_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    id_document_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    id_issued_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    id_expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # KYC enrichment (increment 5; nullable, backfill-free)
    next_of_kin_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_of_kin_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    occupation: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status lifecycle
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    joined_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Portal authentication (Phase 4a). hashed_password stays NULL until the
    # member sets a password via the operator-issued set-password token.
    # portal_enabled is the operator gate; login requires both set plus
    # status='active'.
    hashed_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    portal_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("member_number", name="uq_members_member_number"),
        # PostgreSQL treats NULLs as distinct in UNIQUE constraints — multiple
        # NULL emails/national_id_numbers are allowed (members without one yet).
        UniqueConstraint("email", name="uq_members_email"),
        UniqueConstraint("national_id_number", name="uq_members_national_id_number"),
        CheckConstraint(
            "gender IN ('male', 'female', 'other')",
            name="ck_members_gender",
        ),
        CheckConstraint(
            "status IN ('pending', 'active', 'suspended', 'exited')",
            name="ck_members_status",
        ),
        CheckConstraint(
            "id_document_type IS NULL OR id_document_type IN ('national_id', 'passport', 'driving_license')",
            name="ck_members_id_doc_type",
        ),
        Index("ix_members_status", "status"),
        Index("ix_members_email", "email"),
        Index("ix_members_national_id_number", "national_id_number"),
    )


class MemberKycRequirement(Base):
    """Per-tenant override of a member KYC field's required-ness.

    Override rows only: a missing row means "use the catalog default".
    Locked catalog fields ignore any row here. One row per field_key.
    Tenant-schema twin of platform.sacco_kyc_requirements.
    """

    __tablename__ = "member_kyc_requirements"

    field_key: Mapped[str] = mapped_column(Text, primary_key=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False)


class KycSubmission(AuditableMixin, Base):
    """One member KYC submission awaiting / after operator review.

    At most one 'pending' row per member (partial unique index). Resubmitting
    supersedes the open pending row IN PLACE (new proposed values + refreshed
    submitted_at). Reviewed rows (approved/rejected) are terminal history and
    are never deleted or reused. The proposed-value columns are exactly the
    non-locked MEMBER_KYC_CATALOG keys.
    """

    __tablename__ = "kyc_submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    submitted_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Proposed editable-field snapshot
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    physical_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    national_id_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    id_document_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    id_document_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    id_issued_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    id_expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_of_kin_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_of_kin_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    occupation: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_kyc_submissions_status",
        ),
        CheckConstraint(
            "id_document_type IS NULL OR id_document_type IN ('national_id', 'passport', 'driving_license')",
            name="ck_kyc_submissions_id_doc_type",
        ),
        Index(
            "uq_kyc_submissions_one_pending",
            "member_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_kyc_submissions_status", "status"),
        Index("ix_kyc_submissions_member_id", "member_id"),
    )
