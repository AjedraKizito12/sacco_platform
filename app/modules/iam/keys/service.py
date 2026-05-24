"""KeyService: manage JWT signing key lifecycle.

Maintains two module-level TTL caches (60 s each):
    _active_key_cache       keyed by audience → (kid, private_pem, algorithm)
    _verification_key_cache keyed by kid      → (public_pem, algorithm, audience)

Both caches are shared across all KeyService instances (all instances read
the same platform.jwt_signing_keys table). Call ``clear_key_caches()`` in
tests to prevent cross-test pollution.
"""
from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,  # noqa: TC002 — used at runtime in function signatures
)

from app.core.config import get_settings
from app.modules.iam.keys.crypto import (
    decrypt_private_key,
    encrypt_private_key,
    validate_kek,
)
from app.modules.iam.keys.models import JwtSigningKey

_log = structlog.get_logger(__name__)

_CACHE_TTL = 60.0  # seconds
# retirement threshold: access TTL (15 min) + 60 min safety buffer
_RETIRE_AFTER_MINUTES = 75
_DELETE_AFTER_DAYS = 7


class _TTLCache:
    """Simple dict-backed TTL cache. Safe for concurrent reads under CPython GIL."""

    def __init__(self, ttl: float) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._ttl = ttl

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (value, time.monotonic() + self._ttl)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()


_active_key_cache: _TTLCache = _TTLCache(ttl=_CACHE_TTL)
_verification_key_cache: _TTLCache = _TTLCache(ttl=_CACHE_TTL)


def clear_key_caches() -> None:
    """Clear both in-process caches. Call in tests to prevent cross-test pollution."""
    _active_key_cache.clear()
    _verification_key_cache.clear()


def _generate_rs256_keypair() -> tuple[bytes, bytes]:
    """Return (private_pem, public_pem) as bytes. 2048-bit RSA."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


class KeyService:
    """Manage JWT signing keys.

    Instantiate with a platform-schema ``AsyncSession``.
    Use ``get_platform_session`` for request-scoped usage.
    Open a fresh ``AsyncSessionFactory()`` session for beat tasks.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._kek: bytes = validate_kek(get_settings().jwt_kek)

    async def generate_and_insert(
        self,
        audience: str,
        *,
        kid: str | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> JwtSigningKey:
        """Generate an RS256 keypair and insert it with ``status='active'``.

        Does NOT demote any existing active key — use this for the initial
        bootstrap only. For rotation use ``rotate()``.

        The generated ``kid`` is unique: ``<audience>-<timestamp>-<8-char uuid>``.
        Pass an explicit *kid* to override (useful in migration bootstrap).
        """
        private_pem, public_pem = _generate_rs256_keypair()
        ciphertext, nonce, tag = encrypt_private_key(private_pem, self._kek)

        if kid is None:
            suffix = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
            kid = f"{audience}-{suffix}-{str(uuid.uuid4())[:8]}"

        now = datetime.now(UTC)
        key = JwtSigningKey(
            kid=kid,
            algorithm="RS256",
            audience=audience,
            public_key=public_pem.decode(),
            private_key_encrypted=ciphertext,
            private_key_nonce=nonce,
            private_key_tag=tag,
            status="active",
            created_at=now,
            activated_at=now,
            created_by=actor_id,
        )
        self._session.add(key)
        return key

    async def get_active_signing_key(self, audience: str) -> tuple[str, bytes, str]:
        """Return ``(kid, private_key_pem, algorithm)`` for the active key.

        Result is cached for 60 s. Decrypts the private key on every cache miss.

        Raises ``RuntimeError`` if no active key exists for *audience*.
        """
        cached = _active_key_cache.get(audience)
        if cached is not None:
            return cast(tuple[str, bytes, str], cached)

        result = await self._session.execute(
            select(JwtSigningKey)
            .where(JwtSigningKey.audience == audience)
            .where(JwtSigningKey.status == "active")
            .where(JwtSigningKey.deleted_at.is_(None))
        )
        key = result.scalar_one_or_none()
        if key is None:
            raise RuntimeError(
                f"No active signing key found for audience='{audience}'. "
                "Run: alembic -c alembic/platform/alembic.ini upgrade head"
            )

        private_pem = decrypt_private_key(
            key.private_key_encrypted,
            key.private_key_nonce,
            key.private_key_tag,
            self._kek,
        )
        value = (key.kid, private_pem, key.algorithm)
        _active_key_cache.set(audience, value)
        return value

    async def get_verification_key(self, kid: str) -> tuple[bytes, str, str]:
        """Return ``(public_key_pem, algorithm, audience)`` for *kid*.

        Accepts ``active`` and ``retiring`` keys — both are valid for verifying
        tokens that were issued before the rotation. Rejects ``retired`` and
        soft-deleted keys.

        Result is cached for 60 s.

        Raises ``ValueError`` for retired, deleted, or unknown kids.
        """
        cached = _verification_key_cache.get(kid)
        if cached is not None:
            return cast(tuple[bytes, str, str], cached)

        result = await self._session.execute(
            select(JwtSigningKey).where(JwtSigningKey.kid == kid)
        )
        key = result.scalar_one_or_none()

        if key is None:
            raise ValueError(f"Unknown kid: '{kid}'")
        if key.status == "retired" or key.deleted_at is not None:
            raise ValueError(
                f"Key '{kid}' is retired or deleted — cannot be used for verification"
            )

        value = (key.public_key.encode(), key.algorithm, key.audience)
        _verification_key_cache.set(kid, value)
        return value

    async def rotate(
        self,
        audience: str,
        actor_id: uuid.UUID | None = None,
    ) -> JwtSigningKey:
        """Promote a new key to active; demote the current active key to retiring.

        Returns the new ``JwtSigningKey`` (not yet committed — caller must commit).
        Invalidates the active-key cache entry for *audience* immediately so the
        next signing request picks up the new key.
        """
        result = await self._session.execute(
            select(JwtSigningKey)
            .where(JwtSigningKey.audience == audience)
            .where(JwtSigningKey.status == "active")
        )
        current = result.scalar_one_or_none()
        if current is not None:
            current.status = "retiring"
            current.retired_at = datetime.now(UTC)
            _active_key_cache.invalidate(audience)
            _verification_key_cache.invalidate(current.kid)

        new_key = await self.generate_and_insert(audience=audience, actor_id=actor_id)
        _log.info(
            "iam.key_rotated",
            audience=audience,
            old_kid=current.kid if current else None,
            new_kid=new_key.kid,
            actor_id=str(actor_id) if actor_id else "system",
        )
        return new_key

    async def advance_lifecycle(self, now: datetime) -> dict[str, int]:
        """Advance retiring→retired and soft-delete aged retired keys.

        Retirement threshold: 75 minutes after ``retired_at``
        (access TTL 15 min + 60 min safety buffer ensures no valid access token
        can reference a key that has been retired).

        Soft-delete threshold: 7 days after ``retired_at``.

        Returns ``{"retired": N, "deleted": N}`` for monitoring.
        """
        retire_threshold = now - timedelta(minutes=_RETIRE_AFTER_MINUTES)
        delete_threshold = now - timedelta(days=_DELETE_AFTER_DAYS)

        retiring_result = await self._session.execute(
            select(JwtSigningKey)
            .where(JwtSigningKey.status == "retiring")
            .where(JwtSigningKey.retired_at <= retire_threshold)
        )
        retiring_keys = retiring_result.scalars().all()
        for key in retiring_keys:
            key.status = "retired"
            _verification_key_cache.invalidate(key.kid)

        deleted_result = await self._session.execute(
            select(JwtSigningKey)
            .where(JwtSigningKey.status == "retired")
            .where(JwtSigningKey.deleted_at.is_(None))
            .where(JwtSigningKey.retired_at <= delete_threshold)
        )
        deleted_keys = deleted_result.scalars().all()
        for key in deleted_keys:
            key.deleted_at = now
            _verification_key_cache.invalidate(key.kid)

        return {"retired": len(retiring_keys), "deleted": len(deleted_keys)}


async def verify_boot_keys(
    *,
    _override_session: AsyncSession | None = None,
) -> None:
    """Verify that active signing keys exist for both audiences.

    Called in the FastAPI lifespan when ``PLATFORM_AUTH_MODE=jwt``.
    Raises ``RuntimeError`` if KEK is invalid or any audience lacks an active key.

    Pass ``_override_session`` in tests to avoid opening a new DB connection.
    """
    from sqlalchemy import text

    settings = get_settings()
    validate_kek(settings.jwt_kek)  # fail fast before touching the DB

    async def _check(session: AsyncSession) -> None:
        for audience in ("platform", "tenant"):
            result = await session.execute(
                select(JwtSigningKey)
                .where(JwtSigningKey.audience == audience)
                .where(JwtSigningKey.status == "active")
                .where(JwtSigningKey.deleted_at.is_(None))
            )
            if result.scalar_one_or_none() is None:
                raise RuntimeError(
                    f"No active JWT signing key for audience='{audience}'. "
                    "Run: alembic -c alembic/platform/alembic.ini upgrade head"
                )

    if _override_session is not None:
        await _check(_override_session)
    else:
        from app.core.db import AsyncSessionFactory

        async with AsyncSessionFactory() as session:
            await session.execute(text("SET LOCAL search_path TO platform"))
            await _check(session)

    _log.info("iam.boot_check_passed", mode="jwt")
