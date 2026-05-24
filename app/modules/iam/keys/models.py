"""SQLAlchemy model for platform.jwt_signing_keys."""
from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003 — used at runtime by SQLAlchemy column definitions

from sqlalchemy import CheckConstraint, Index, Text
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import BYTEA, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit.mixin import AuditableMixin
from app.core.db import Base


class JwtSigningKey(AuditableMixin, Base):
    """Asymmetric signing key for JWT issuance.

    Private key material is stored AES-256-GCM encrypted under the KEK from
    ``JWT_KEK``. The 12-byte nonce and 16-byte GCM auth tag are stored in
    dedicated columns so they can be passed directly to ``decrypt_private_key``.

    The partial unique index ``uq_jwt_signing_keys_active_per_audience``
    enforces at most one row with ``status='active'`` per audience at the DB
    level — the application must rely on this, not application-level logic alone.

    Lifecycle::

        active → retiring  (new key is rotated in; old key starts retiring)
        retiring → retired (advance_lifecycle promotes after ≥ 75 min: 15 min
                            access TTL + 60 min safety buffer)
        retired  → soft-deleted via deleted_at (after 7-day buffer)
    """

    __tablename__ = "jwt_signing_keys"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'retiring', 'retired')",
            name="ck_jwt_signing_keys_status",
        ),
        CheckConstraint(
            "algorithm IN ('RS256', 'EdDSA')",
            name="ck_jwt_signing_keys_algorithm",
        ),
        CheckConstraint(
            "audience IN ('platform', 'tenant')",
            name="ck_jwt_signing_keys_audience",
        ),
        # DB-level enforcement: at most one active key per audience.
        Index(
            "uq_jwt_signing_keys_active_per_audience",
            "audience",
            unique=True,
            postgresql_where=sa_text("status = 'active'"),
        ),
        Index("ix_jwt_signing_keys_kid", "kid"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    kid: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    algorithm: Mapped[str] = mapped_column(Text, nullable=False)
    audience: Mapped[str] = mapped_column(Text, nullable=False)
    # Public key in PEM format — safe to store and log; never encrypted.
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    # Private key encrypted with KEK via AES-256-GCM.
    private_key_encrypted: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    private_key_nonce: Mapped[bytes] = mapped_column(BYTEA, nullable=False)   # 12 bytes
    private_key_tag: Mapped[bytes] = mapped_column(BYTEA, nullable=False)     # 16 bytes
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    # Null for system-generated keys (migration bootstrap, beat rotation).
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
