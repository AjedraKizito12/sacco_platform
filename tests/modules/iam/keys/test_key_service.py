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
from app.modules.iam.keys.service import KeyService, clear_key_caches, verify_boot_keys


def _factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s:
        await s.execute(text("SET search_path TO platform"))
        await s.execute(delete(PlatformAuditLog))
        await s.execute(delete(JwtSigningKey))
        await s.commit()


@pytest.fixture(autouse=True)
def reset_key_caches():
    """Prevent cross-test cache pollution."""
    clear_key_caches()
    yield
    clear_key_caches()


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


@pytest.mark.anyio
async def test_generate_and_insert_creates_active_rs256_key(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    try:
        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            svc = KeyService(s)
            key = await svc.generate_and_insert(audience="platform")
            await s.commit()

            assert key.status == "active"
            assert key.algorithm == "RS256"
            assert key.audience == "platform"
            assert key.kid.startswith("platform-")
            assert "PUBLIC KEY" in key.public_key
            assert len(key.private_key_nonce) == 12
            assert len(key.private_key_tag) == 16
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_get_active_signing_key_returns_decrypted_pem(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    try:
        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            svc = KeyService(s)
            await svc.generate_and_insert(audience="platform")
            await s.commit()

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            svc = KeyService(s)
            kid, private_pem, algorithm = await svc.get_active_signing_key("platform")

            assert kid.startswith("platform-")
            assert b"PRIVATE KEY" in private_pem
            assert algorithm == "RS256"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_get_active_signing_key_raises_when_no_key_exists(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    try:
        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            svc = KeyService(s)
            with pytest.raises(RuntimeError, match="No active signing key"):
                await svc.get_active_signing_key("platform")
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_get_verification_key_returns_public_pem_for_active_key(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    try:
        kid_ref = None
        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            svc = KeyService(s)
            key = await svc.generate_and_insert(audience="platform")
            await s.commit()
            kid_ref = key.kid

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            svc = KeyService(s)
            public_pem, algorithm, audience = await svc.get_verification_key(kid_ref)

            assert b"PUBLIC KEY" in public_pem
            assert algorithm == "RS256"
            assert audience == "platform"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_get_verification_key_accepts_retiring_status(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    try:
        kid_ref = None
        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            svc = KeyService(s)
            key = await svc.generate_and_insert(audience="platform")
            await s.commit()
            kid_ref = key.kid

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            result = await s.execute(select(JwtSigningKey).where(JwtSigningKey.kid == kid_ref))
            key = result.scalar_one()
            key.status = "retiring"
            await s.commit()

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            svc = KeyService(s)
            public_pem, _, _ = await svc.get_verification_key(kid_ref)
            assert b"PUBLIC KEY" in public_pem
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_get_verification_key_rejects_retired_key(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    try:
        kid_ref = None
        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            svc = KeyService(s)
            key = await svc.generate_and_insert(audience="platform")
            await s.commit()
            kid_ref = key.kid

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            result = await s.execute(select(JwtSigningKey).where(JwtSigningKey.kid == kid_ref))
            key = result.scalar_one()
            key.status = "retired"
            await s.commit()

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            svc = KeyService(s)
            with pytest.raises(ValueError, match="retired"):
                await svc.get_verification_key(kid_ref)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_get_verification_key_raises_for_unknown_kid(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    try:
        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            svc = KeyService(s)
            with pytest.raises(ValueError, match="Unknown kid"):
                await svc.get_verification_key("does-not-exist")
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_verify_boot_keys_passes_when_active_keys_exist(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    try:
        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            svc = KeyService(s)
            await svc.generate_and_insert(audience="platform")
            await svc.generate_and_insert(audience="tenant")
            await s.commit()

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            await verify_boot_keys(_override_session=s)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_verify_boot_keys_raises_when_platform_key_missing(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    try:
        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            svc = KeyService(s)
            await svc.generate_and_insert(audience="tenant")
            await s.commit()

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            with pytest.raises(RuntimeError, match="platform"):
                await verify_boot_keys(_override_session=s)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_verify_boot_keys_raises_when_no_keys_exist(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    try:
        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            with pytest.raises(RuntimeError, match="No active JWT signing key"):
                await verify_boot_keys(_override_session=s)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_rotate_promotes_new_key_and_demotes_current_to_retiring(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    try:
        original_kid = None
        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            svc = KeyService(s)
            original = await svc.generate_and_insert(audience="platform")
            await s.commit()
            original_kid = original.kid

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            svc = KeyService(s)
            new_key = await svc.rotate(audience="platform")
            await s.commit()

            assert new_key.status == "active"
            assert new_key.kid != original_kid

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            result = await s.execute(
                select(JwtSigningKey).where(JwtSigningKey.kid == original_kid)
            )
            original = result.scalar_one()
            assert original.status == "retiring"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_rotate_with_no_existing_key_creates_first_active_key(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    try:
        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            svc = KeyService(s)
            new_key = await svc.rotate(audience="tenant")
            await s.commit()

            assert new_key.status == "active"
            assert new_key.audience == "tenant"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_advance_lifecycle_retires_old_retiring_keys(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    try:
        kid_ref = None
        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            svc = KeyService(s)
            key = await svc.generate_and_insert(audience="platform")
            await s.commit()
            kid_ref = key.kid

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            result = await s.execute(select(JwtSigningKey).where(JwtSigningKey.kid == kid_ref))
            key = result.scalar_one()
            key.status = "retiring"
            key.retired_at = datetime.now(UTC) - timedelta(hours=2)
            await s.commit()

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            svc = KeyService(s)
            counts = await svc.advance_lifecycle(datetime.now(UTC))
            await s.commit()

            assert counts["retired"] == 1

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            result = await s.execute(select(JwtSigningKey).where(JwtSigningKey.kid == kid_ref))
            key = result.scalar_one()
            assert key.status == "retired"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_advance_lifecycle_soft_deletes_aged_retired_keys(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    try:
        kid_ref = None
        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            svc = KeyService(s)
            key = await svc.generate_and_insert(audience="platform")
            await s.commit()
            kid_ref = key.kid

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            result = await s.execute(select(JwtSigningKey).where(JwtSigningKey.kid == kid_ref))
            key = result.scalar_one()
            key.status = "retired"
            key.retired_at = datetime.now(UTC) - timedelta(days=8)
            await s.commit()

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            svc = KeyService(s)
            counts = await svc.advance_lifecycle(datetime.now(UTC))
            await s.commit()

            assert counts["deleted"] == 1

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            result = await s.execute(select(JwtSigningKey).where(JwtSigningKey.kid == kid_ref))
            key = result.scalar_one()
            assert key.deleted_at is not None
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_advance_lifecycle_ignores_recently_retiring_keys(test_engine: AsyncEngine):
    factory = _factory(test_engine)
    try:
        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            svc = KeyService(s)
            key = await svc.generate_and_insert(audience="platform")
            await s.commit()
            kid_ref = key.kid

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            result = await s.execute(select(JwtSigningKey).where(JwtSigningKey.kid == kid_ref))
            key = result.scalar_one()
            key.status = "retiring"
            key.retired_at = datetime.now(UTC) - timedelta(minutes=10)
            await s.commit()

        async with factory() as s:
            await s.execute(text("SET search_path TO platform"))
            svc = KeyService(s)
            counts = await svc.advance_lifecycle(datetime.now(UTC))
            assert counts["retired"] == 0
            assert counts["deleted"] == 0
    finally:
        await _cleanup(factory)
