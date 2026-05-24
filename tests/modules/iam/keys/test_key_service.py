"""Tests for JwtSigningKey model and KeyService.

These tests use `async_sessionmaker` + `commit()` instead of the
`platform_session` fixture because JwtSigningKey uses AuditableMixin,
which fires SQLAlchemy events during flush. The connection-bound session
in `platform_session` conflicts with asyncpg when the event handler adds
audit rows during an in-progress async flush. This matches the pattern
used in tests/core/audit/test_audit_mixin.py.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.audit.models import PlatformAuditLog
from app.modules.iam.keys.models import JwtSigningKey


def _factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s:
        await s.execute(text("SET search_path TO platform"))
        await s.execute(delete(PlatformAuditLog))
        await s.execute(delete(JwtSigningKey))
        await s.commit()


@pytest.mark.anyio
async def test_jwt_signing_key_model_persists(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    kid = f"platform-test-{uuid.uuid4().hex[:8]}"

    try:
        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            key = JwtSigningKey(
                kid=kid,
                algorithm="RS256",
                audience="platform",
                public_key="-----BEGIN PUBLIC KEY-----\nfake\n-----END PUBLIC KEY-----\n",
                private_key_encrypted=b"\x00" * 32,
                private_key_nonce=b"\x00" * 12,
                private_key_tag=b"\x00" * 16,
                status="active",
                created_at=datetime.now(UTC),
            )
            s.add(key)
            await s.commit()

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            result = await s.execute(select(JwtSigningKey).where(JwtSigningKey.kid == kid))
            fetched = result.scalar_one()
            assert fetched.algorithm == "RS256"
            assert fetched.audience == "platform"
            assert fetched.status == "active"
            assert isinstance(fetched.id, uuid.UUID)
            assert fetched.private_key_encrypted == b"\x00" * 32
    finally:
        await _cleanup(factory)
