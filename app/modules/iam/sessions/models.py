"""SQLAlchemy models for server-side session tracking.

Two models — PlatformSession (platform schema) and TenantSession (no schema,
resolved via search_path) — share an identical column layout. The only
structural difference is the user FK column name.

Sessions are NOT auditable (no AuditableMixin). Auth audit events are written
explicitly in the auth service layer (Plan 11) rather than by the ORM hook,
because the audit record needs richer context (IP, user agent, reason) than
the generic mixin captures.
"""
from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003 — used at runtime by SQLAlchemy

from sqlalchemy import Index, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class PlatformSession(Base):
    """Server-side session for a platform user.

    ``id`` is used as the ``session_id`` claim in the JWT so the session row
    can be fetched directly by primary key on every authenticated request.

    ``jti`` is the refresh token's JWT ID — stored here so the refresh token
    can be revoked individually (delete the Redis jti key; set revoked_at).
    """

    __tablename__ = "platform_sessions"
    __table_args__ = (
        Index("ix_platform_sessions_platform_user_id", "platform_user_id"),
        Index("ix_platform_sessions_jti", "jti"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    platform_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    jti: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class TenantSession(Base):
    """Server-side session for a tenant user.

    Identical layout to PlatformSession except the user FK column is
    ``tenant_user_id``. Lives in the tenant schema — no ``schema=`` in
    ``__table_args__``; resolved at runtime via ``SET LOCAL search_path``.
    """

    __tablename__ = "tenant_sessions"
    __table_args__ = (
        Index("ix_tenant_sessions_tenant_user_id", "tenant_user_id"),
        Index("ix_tenant_sessions_jti", "jti"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    jti: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class MemberSession(Base):
    """Server-side session for a SACCO member (portal login, Phase 4a).

    Identical layout to TenantSession except the user FK column is
    ``member_id``. Lives in the tenant schema — no ``schema=``; resolved at
    runtime via ``SET LOCAL search_path``.
    """

    __tablename__ = "member_sessions"
    __table_args__ = (
        Index("ix_member_sessions_member_id", "member_id"),
        Index("ix_member_sessions_jti", "jti"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    jti: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
