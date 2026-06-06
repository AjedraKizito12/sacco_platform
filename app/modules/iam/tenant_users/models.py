"""SQLAlchemy model for the tenant_users table.

Lives in the tenant schema — no ``schema=`` in ``__table_args__``.
Search path is set by ``get_tenant_session`` before any query runs.

Carries ``AuditableMixin`` so that every insert, update, and delete writes
a row to the tenant's ``audit_log`` with ``actor_type='tenant_user'``
(or ``'platform_user'`` when a platform actor is the active context var).

``hashed_password`` is ``null`` until the user completes the password reset
flow (Plan 08). Authentication is blocked for users with null password.

``is_admin`` is a coarse gate used by all downstream modules until the full
role/permission system ships in IAM v2.
"""
from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003 — used at runtime by SQLAlchemy

from sqlalchemy import Boolean, Index, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit.mixin import AuditableMixin
from app.core.db import Base


class TenantUser(AuditableMixin, Base):
    __tablename__ = "tenant_users"
    __table_args__ = (
        Index("ix_tenant_users_email", "email"),
        # No schema= — resolved at runtime via SET LOCAL search_path.
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    # Null until the user sets a password via the reset flow (Plan 08).
    hashed_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Coarse superuser gate; replaced by the permission system in IAM v2.
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Populated by 02b's shadow-user creation. NULL for real tenant users.
    impersonation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
