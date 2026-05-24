# IAM v1-01: JWT Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement JWT signing key management (platform.jwt_signing_keys, AES-256-GCM envelope encryption, KeyService), token encode/decode (TokenService, PyJWT RS256), the public JWKS discovery endpoint, Celery beat jobs for automated rotation and lifecycle advancement, and the startup boot check that validates keys exist when `PLATFORM_AUTH_MODE=jwt`.

**Architecture:** Asymmetric RS256 keypairs are stored in `platform.jwt_signing_keys` with private keys encrypted under a 32-byte KEK from `JWT_KEK` env (AES-256-GCM). A module-level TTL cache (60 s) in `KeyService` avoids per-request DB hits. `TokenService` uses PyJWT for encode/decode with `kid` in the JWT header for key selection. `GET /.well-known/jwks.json` returns active + retiring public keys in JWK Set format. Two Celery beat jobs — `advance_key_lifecycle` (hourly) and `rotate_signing_keys_if_due` (daily) — automate key lifecycle. `verify_boot_keys()` is called in the FastAPI lifespan when `PLATFORM_AUTH_MODE=jwt`.

**Tech Stack:** SQLAlchemy 2.0 async, PyJWT ≥ 2.8, cryptography ≥ 42 (pyca), Alembic, Celery 5 + `asyncio.run()` bridge, FastAPI, pytest-anyio

---

## Required Reading (complete before starting any task)

1. `CLAUDE.md` — architectural rules, multi-tenancy, audit requirements
2. `docs/superpowers/decisions/2026-05-21-iam-architecture.md` — ADR: RS256/EdDSA decision, audience separation, key lifecycle, dependency freeze
3. `docs/superpowers/specs/2026-05-21-iam-v1-design.md` §3.1 and §4.1–4.5 — data model and JWT infrastructure spec
4. `app/core/config.py` — existing `Settings` shape (pydantic-settings `BaseSettings`)
5. `app/core/db.py` — `Base`, `AsyncSessionFactory`, `get_platform_session`
6. `app/core/audit/mixin.py` — `AuditableMixin` (`JwtSigningKey` uses it)
7. `app/platform_/models.py` — `PlatformUser` (referenced by `created_by` FK, and used by the key management API)
8. `app/platform_/auth.py` — `get_current_superuser` (used to gate the admin key list endpoint)
9. `app/workers/celery_app.py` — existing `@celery_app.task` / `asyncio.run()` pattern
10. `app/main.py` — lifespan function (boot check goes here), existing router includes
11. `tests/conftest.py` — `platform_session`, `anyio_backend`, `test_engine` fixtures

---

## File Map

```
CREATE app/modules/iam/__init__.py
CREATE app/modules/iam/keys/__init__.py
CREATE app/modules/iam/keys/crypto.py        — AES-256-GCM encrypt/decrypt, validate_kek
CREATE app/modules/iam/keys/models.py        — JwtSigningKey SQLAlchemy model (platform schema)
CREATE app/modules/iam/keys/service.py       — KeyService + verify_boot_keys()
CREATE app/modules/iam/keys/schemas.py       — JwkOut, JwksResponse, JwtKeyOut
CREATE app/modules/iam/keys/api.py           — GET /.well-known/jwks.json; GET /platform/jwt-keys/
CREATE app/modules/iam/tokens/__init__.py
CREATE app/modules/iam/tokens/service.py     — encode_access_token, encode_refresh_token, decode_token, get_unverified_kid
CREATE app/modules/iam/beat.py               — advance_key_lifecycle, rotate_signing_keys_if_due Celery tasks
CREATE alembic/platform/versions/003_iam_platform.py  — jwt_signing_keys DDL + bootstrap keypairs
CREATE tests/modules/iam/__init__.py
CREATE tests/modules/iam/keys/__init__.py
CREATE tests/modules/iam/keys/test_crypto.py
CREATE tests/modules/iam/keys/test_key_service.py
CREATE tests/modules/iam/tokens/__init__.py
CREATE tests/modules/iam/tokens/test_token_service.py
MODIFY app/core/config.py         — add JWT settings and field_validator for jwt_kek
MODIFY app/workers/celery_app.py  — add "app.modules.iam.beat" to include list + beat schedule entries
MODIFY app/main.py                — include jwks_router + key_mgmt_router; call verify_boot_keys() in lifespan
MODIFY tests/conftest.py          — add JWT_KEK env default; import iam keys model into test_engine
```

---

### Task 1: JWT configuration settings

**Files:**
- Modify: `app/core/config.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write the failing tests**

Add these four tests to the existing `tests/core/test_config.py`:

```python
import base64
import pytest


def test_jwt_kek_validator_rejects_wrong_length():
    from pydantic import ValidationError
    from app.core.config import Settings

    with pytest.raises(ValidationError, match="32 bytes"):
        Settings(
            database_url="postgresql+asyncpg://x:x@localhost/x",
            app_secret_key="x",
            jwt_kek=base64.b64encode(b"tooshort").decode(),
        )


def test_jwt_kek_validator_rejects_bad_base64():
    from pydantic import ValidationError
    from app.core.config import Settings

    with pytest.raises(ValidationError, match="base64"):
        Settings(
            database_url="postgresql+asyncpg://x:x@localhost/x",
            app_secret_key="x",
            jwt_kek="!!!not-valid-base64!!!",
        )


def test_jwt_kek_validator_accepts_empty_string():
    # Empty is allowed; the lifespan check catches the jwt+empty combination at boot.
    from app.core.config import Settings

    s = Settings(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        app_secret_key="x",
        jwt_kek="",
    )
    assert s.jwt_kek == ""


def test_jwt_kek_validator_accepts_valid_32_byte_key():
    from app.core.config import Settings

    kek = base64.b64encode(b"\xab" * 32).decode()
    s = Settings(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        app_secret_key="x",
        jwt_kek=kek,
    )
    assert s.jwt_kek == kek
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/core/test_config.py -v -k "jwt_kek"
```

Expected: `AttributeError` or `ValidationError` — `jwt_kek` field not yet on `Settings`

- [ ] **Step 3: Replace `app/core/config.py` with the updated version**

```python
import base64
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # Elasticsearch
    elasticsearch_url: str = "http://localhost:9200"

    # App
    app_secret_key: str
    app_env: str = "development"
    log_level: str = "INFO"
    allowed_origins: list[str] = ["http://localhost:3000"]

    # DB pool
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Observability
    structlog_json: bool = False
    slow_query_ms: int = 200

    # Headers
    request_id_header: str = "X-Request-ID"
    tenant_header: str = "X-Tenant-Slug"

    # Outbox retention
    outbox_retention_days: int = 90

    # Platform auth
    platform_auth_mode: str = "stub"  # "stub" | "jwt"
    platform_bootstrap_email: str = ""
    platform_bootstrap_full_name: str = "Platform Admin"

    # Tenant auth
    tenant_auth_mode: str = "stub"  # "stub" | "jwt"

    # JWT signing key infrastructure
    jwt_kek: str = ""  # base64-encoded 32-byte key-encryption-key; required when auth_mode=jwt
    jwt_key_rotation_days: int = 90
    jwt_access_ttl_seconds: int = 900             # 15 min
    jwt_refresh_ttl_platform_seconds: int = 3600  # 1 h
    jwt_refresh_ttl_tenant_seconds: int = 28800   # 8 h

    @field_validator("jwt_kek")
    @classmethod
    def validate_jwt_kek(cls, v: str) -> str:
        if not v:
            return v  # empty is permitted; lifespan rejects the jwt+empty combination at boot
        try:
            decoded = base64.b64decode(v, validate=True)
        except Exception:
            raise ValueError("JWT_KEK must be valid base64")
        if len(decoded) != 32:
            raise ValueError(
                f"JWT_KEK must decode to exactly 32 bytes; got {len(decoded)}"
            )
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Add JWT_KEK default to `tests/conftest.py`**

Add two lines after the existing `os.environ.setdefault` block (around line 17):

```python
os.environ.setdefault("JWT_KEK", base64.b64encode(b"\x01" * 32).decode())
os.environ.setdefault("TENANT_AUTH_MODE", "stub")
```

And add the `base64` import to the top of `tests/conftest.py` if not already present:

```python
import base64
```

Also add an import inside the `test_engine` fixture body, directly after the `from app.core.db import Base` line, to register `JwtSigningKey` in `Base.metadata` so `create_all` creates the table:

```python
import app.modules.iam.keys.models  # noqa: F401 — registers JwtSigningKey in Base.metadata
```

- [ ] **Step 5: Run tests to confirm pass**

```bash
pytest tests/core/test_config.py -v -k "jwt_kek"
```

Expected: 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/core/config.py tests/conftest.py tests/core/test_config.py
git commit -m "feat(iam): add JWT config settings with KEK field-validator and test env defaults"
```

---

### Task 2: AES-256-GCM envelope encryption utilities

**Files:**
- Create: `app/modules/iam/__init__.py`
- Create: `app/modules/iam/keys/__init__.py`
- Create: `app/modules/iam/tokens/__init__.py`
- Create: `app/modules/iam/keys/crypto.py`
- Create: `tests/modules/iam/__init__.py`
- Create: `tests/modules/iam/keys/__init__.py`
- Create: `tests/modules/iam/tokens/__init__.py`
- Create: `tests/modules/iam/keys/test_crypto.py`

- [ ] **Step 1: Create empty `__init__.py` files and directory structure**

```bash
mkdir -p app/modules/iam/keys app/modules/iam/tokens
touch app/modules/iam/__init__.py app/modules/iam/keys/__init__.py app/modules/iam/tokens/__init__.py
mkdir -p tests/modules/iam/keys tests/modules/iam/tokens
touch tests/modules/iam/__init__.py tests/modules/iam/keys/__init__.py tests/modules/iam/tokens/__init__.py
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/modules/iam/keys/test_crypto.py
import base64
import os

import pytest

from app.modules.iam.keys.crypto import decrypt_private_key, encrypt_private_key, validate_kek


def test_encrypt_decrypt_round_trip():
    kek = os.urandom(32)
    pem = b"-----BEGIN PRIVATE KEY-----\nfakekey\n-----END PRIVATE KEY-----\n"
    ciphertext, nonce, tag = encrypt_private_key(pem, kek)
    recovered = decrypt_private_key(ciphertext, nonce, tag, kek)
    assert recovered == pem


def test_nonce_is_unique_per_call():
    kek = os.urandom(32)
    pem = b"same-data"
    _, nonce1, _ = encrypt_private_key(pem, kek)
    _, nonce2, _ = encrypt_private_key(pem, kek)
    assert nonce1 != nonce2


def test_wrong_kek_raises_value_error():
    kek = os.urandom(32)
    wrong_kek = os.urandom(32)
    pem = b"secret"
    ciphertext, nonce, tag = encrypt_private_key(pem, kek)
    with pytest.raises(ValueError, match="Decryption failed"):
        decrypt_private_key(ciphertext, nonce, tag, wrong_kek)


def test_tampered_ciphertext_raises_value_error():
    kek = os.urandom(32)
    pem = b"secret"
    ciphertext, nonce, tag = encrypt_private_key(pem, kek)
    bad = bytes([ciphertext[0] ^ 0xFF]) + ciphertext[1:]
    with pytest.raises(ValueError, match="Decryption failed"):
        decrypt_private_key(bad, nonce, tag, kek)


def test_validate_kek_accepts_valid_32_byte_b64():
    raw = os.urandom(32)
    result = validate_kek(base64.b64encode(raw).decode())
    assert result == raw
    assert len(result) == 32


def test_validate_kek_rejects_wrong_decoded_length():
    with pytest.raises(ValueError, match="32 bytes"):
        validate_kek(base64.b64encode(b"tooshort").decode())


def test_validate_kek_rejects_invalid_base64():
    with pytest.raises(ValueError, match="base64"):
        validate_kek("!!!not-valid!!!")
```

- [ ] **Step 3: Run tests to confirm failure**

```bash
pytest tests/modules/iam/keys/test_crypto.py -v
```

Expected: `ImportError` — `crypto.py` does not exist yet

- [ ] **Step 4: Create `app/modules/iam/keys/crypto.py`**

```python
"""AES-256-GCM envelope encryption for JWT signing private keys.

The private key PEM is encrypted under a Key Encryption Key (KEK) supplied as
a base64-encoded 32-byte value from the ``JWT_KEK`` environment variable.

Each encryption call generates a fresh 12-byte nonce (GCM-recommended length).
The 16-byte GCM authentication tag is returned separately so it can be stored
in its own BYTEA column on the jwt_signing_keys table.
"""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def encrypt_private_key(pem: bytes, kek: bytes) -> tuple[bytes, bytes, bytes]:
    """Encrypt *pem* under *kek* using AES-256-GCM.

    Returns ``(ciphertext, nonce, tag)`` — three separate byte strings
    suitable for storing in dedicated BYTEA columns.

    The ``cryptography`` library appends the 16-byte GCM auth tag to the
    ciphertext. This function splits them so callers can store them
    independently and avoid having to know the internal layout.
    """
    nonce = os.urandom(12)
    aesgcm = AESGCM(kek)
    ct_with_tag = aesgcm.encrypt(nonce, pem, None)
    ciphertext = ct_with_tag[:-16]
    tag = ct_with_tag[-16:]
    return ciphertext, nonce, tag


def decrypt_private_key(
    ciphertext: bytes,
    nonce: bytes,
    tag: bytes,
    kek: bytes,
) -> bytes:
    """Decrypt *ciphertext* using *kek*, verifying the GCM auth *tag*.

    Raises ``ValueError`` if the tag does not match (wrong KEK or corrupted
    ciphertext). The error message is deliberately generic to avoid leaking
    information about whether the KEK or the ciphertext is wrong.
    """
    aesgcm = AESGCM(kek)
    ct_with_tag = ciphertext + tag
    try:
        return aesgcm.decrypt(nonce, ct_with_tag, None)
    except Exception as exc:
        raise ValueError("Decryption failed: invalid KEK or corrupted data") from exc


def validate_kek(kek_b64: str) -> bytes:
    """Decode and validate a base64-encoded KEK string.

    Returns the raw 32-byte key. Raises ``ValueError`` if the string is not
    valid base64 or does not decode to exactly 32 bytes.
    """
    try:
        kek = base64.b64decode(kek_b64, validate=True)
    except Exception:
        raise ValueError("JWT_KEK must be valid base64")
    if len(kek) != 32:
        raise ValueError(
            f"JWT_KEK must decode to exactly 32 bytes; got {len(kek)}"
        )
    return kek
```

- [ ] **Step 5: Run tests to confirm pass**

```bash
pytest tests/modules/iam/keys/test_crypto.py -v
```

Expected: 7 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/modules/iam/ tests/modules/iam/
git commit -m "feat(iam): AES-256-GCM envelope encryption utilities for JWT private keys"
```

---

### Task 3: JwtSigningKey SQLAlchemy model

**Files:**
- Create: `app/modules/iam/keys/models.py`
- Create: `tests/modules/iam/keys/test_key_service.py` (stub — model test only; expanded in Task 5)

- [ ] **Step 1: Write the failing test**

```python
# tests/modules/iam/keys/test_key_service.py
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.modules.iam.keys.models import JwtSigningKey


@pytest.mark.anyio
async def test_jwt_signing_key_model_persists(platform_session):
    key = JwtSigningKey(
        kid="platform-2026-001",
        algorithm="RS256",
        audience="platform",
        public_key="-----BEGIN PUBLIC KEY-----\nfake\n-----END PUBLIC KEY-----\n",
        private_key_encrypted=b"\x00" * 32,
        private_key_nonce=b"\x00" * 12,
        private_key_tag=b"\x00" * 16,
        status="active",
        created_at=datetime.now(UTC),
    )
    platform_session.add(key)
    await platform_session.flush()

    result = await platform_session.execute(
        select(JwtSigningKey).where(JwtSigningKey.kid == "platform-2026-001")
    )
    fetched = result.scalar_one()
    assert fetched.algorithm == "RS256"
    assert fetched.audience == "platform"
    assert fetched.status == "active"
    assert isinstance(fetched.id, uuid.UUID)
    assert fetched.private_key_encrypted == b"\x00" * 32
```

- [ ] **Step 2: Run test to confirm failure**

```bash
pytest tests/modules/iam/keys/test_key_service.py::test_jwt_signing_key_model_persists -v
```

Expected: `ImportError` — `models.py` does not exist yet

- [ ] **Step 3: Create `app/modules/iam/keys/models.py`**

```python
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
```

- [ ] **Step 4: Run test to confirm pass**

```bash
pytest tests/modules/iam/keys/test_key_service.py::test_jwt_signing_key_model_persists -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/modules/iam/keys/models.py tests/modules/iam/keys/test_key_service.py
git commit -m "feat(iam): JwtSigningKey model — platform schema, BYTEA private key columns, partial unique index"
```

---

### Task 4: Platform migration 003 — jwt_signing_keys DDL + bootstrap keypairs

**Files:**
- Create: `alembic/platform/versions/003_iam_platform.py`

This migration creates `platform.jwt_signing_keys` and bootstraps one RS256 keypair per
audience (`platform` and `tenant`). It reads `JWT_KEK` from env and fails if it is absent
or invalid. The bootstrap is idempotent — it checks for an existing `kid` before inserting.

- [ ] **Step 1: Verify the migration chain**

```bash
ls alembic/platform/versions/
```

Expected output: `001_core_platform.py  002_platform_module.py`

- [ ] **Step 2: Create `alembic/platform/versions/003_iam_platform.py`**

```python
"""Create platform.jwt_signing_keys; bootstrap initial RS256 keypairs.

Revision: 003
Depends on: 002 (platform_users must exist before adding created_by reference)

Bootstrap behaviour:
    Reads JWT_KEK from env. Fails with RuntimeError if absent or invalid.
    Generates one RS256-2048 keypair per audience ('platform', 'tenant').
    Inserts each as status='active'. Idempotent: skips if the target kid
    already exists in the table.
"""
from __future__ import annotations

import base64
import os
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def _get_kek() -> bytes:
    kek_b64 = os.environ.get("JWT_KEK", "")
    if not kek_b64:
        raise RuntimeError(
            "JWT_KEK environment variable is required to run migration 003. "
            "Generate one: python -c \"import os,base64; print(base64.b64encode(os.urandom(32)).decode())\""
        )
    try:
        kek = base64.b64decode(kek_b64, validate=True)
    except Exception as exc:
        raise RuntimeError("JWT_KEK is not valid base64") from exc
    if len(kek) != 32:
        raise RuntimeError(
            f"JWT_KEK must decode to exactly 32 bytes; got {len(kek)}"
        )
    return kek


def _generate_rs256_keypair() -> tuple[bytes, bytes]:
    """Return (private_key_pem, public_key_pem)."""
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


def _aes_gcm_encrypt(pem: bytes, kek: bytes) -> tuple[bytes, bytes, bytes]:
    """Return (ciphertext, nonce, tag). Inline copy — avoids importing app code in migrations."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    aesgcm = AESGCM(kek)
    ct_with_tag = aesgcm.encrypt(nonce, pem, None)
    return ct_with_tag[:-16], nonce, ct_with_tag[-16:]


def upgrade() -> None:
    op.create_table(
        "jwt_signing_keys",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("kid", sa.Text(), nullable=False),
        sa.Column("algorithm", sa.Text(), nullable=False),
        sa.Column("audience", sa.Text(), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("private_key_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("private_key_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("private_key_tag", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("activated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("retired_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'retiring', 'retired')",
            name="ck_jwt_signing_keys_status",
        ),
        sa.CheckConstraint(
            "algorithm IN ('RS256', 'EdDSA')",
            name="ck_jwt_signing_keys_algorithm",
        ),
        sa.CheckConstraint(
            "audience IN ('platform', 'tenant')",
            name="ck_jwt_signing_keys_audience",
        ),
        sa.UniqueConstraint("kid", name="uq_jwt_signing_keys_kid"),
        schema="platform",
    )
    op.create_index(
        "uq_jwt_signing_keys_active_per_audience",
        "jwt_signing_keys",
        ["audience"],
        unique=True,
        schema="platform",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_jwt_signing_keys_kid",
        "jwt_signing_keys",
        ["kid"],
        schema="platform",
    )

    # Bootstrap: one active keypair per audience (idempotent).
    kek = _get_kek()
    conn = op.get_bind()
    now = datetime.now(UTC)

    for audience in ("platform", "tenant"):
        kid = f"{audience}-2026-001"

        existing = conn.execute(
            sa.text("SELECT id FROM platform.jwt_signing_keys WHERE kid = :kid"),
            {"kid": kid},
        ).fetchone()
        if existing:
            continue

        private_pem, public_pem = _generate_rs256_keypair()
        ciphertext, nonce, tag = _aes_gcm_encrypt(private_pem, kek)

        conn.execute(
            sa.text(
                """
                INSERT INTO platform.jwt_signing_keys
                    (kid, algorithm, audience, public_key,
                     private_key_encrypted, private_key_nonce, private_key_tag,
                     status, created_at, activated_at)
                VALUES
                    (:kid, 'RS256', :audience, :public_key,
                     :ciphertext, :nonce, :tag,
                     'active', :now, :now)
                """
            ),
            {
                "kid": kid,
                "audience": audience,
                "public_key": public_pem.decode(),
                "ciphertext": ciphertext,
                "nonce": nonce,
                "tag": tag,
                "now": now,
            },
        )


def downgrade() -> None:
    op.drop_index(
        "uq_jwt_signing_keys_active_per_audience",
        table_name="jwt_signing_keys",
        schema="platform",
    )
    op.drop_index(
        "ix_jwt_signing_keys_kid",
        table_name="jwt_signing_keys",
        schema="platform",
    )
    op.drop_table("jwt_signing_keys", schema="platform")
```

- [ ] **Step 3: Verify the file is importable (syntax check)**

```bash
python -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('m003', 'alembic/platform/versions/003_iam_platform.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print('revision:', m.revision, '— OK')
"
```

Expected output: `revision: 003 — OK`

- [ ] **Step 4: Commit**

```bash
git add alembic/platform/versions/003_iam_platform.py
git commit -m "feat(iam): migration 003 — jwt_signing_keys table with RS256 bootstrap keypairs"
```

---

### Task 5: KeyService — generate, get_active, get_verification, verify_boot_keys

**Files:**
- Create: `app/modules/iam/keys/service.py`
- Modify: `tests/modules/iam/keys/test_key_service.py`

- [ ] **Step 1: Add the new tests**

Append the following to `tests/modules/iam/keys/test_key_service.py`:

```python
import pytest
from datetime import UTC, datetime

from app.modules.iam.keys.service import KeyService, clear_key_caches, verify_boot_keys


@pytest.fixture(autouse=True)
def reset_key_caches():
    """Prevent cross-test cache pollution."""
    clear_key_caches()
    yield
    clear_key_caches()


@pytest.mark.anyio
async def test_generate_and_insert_creates_active_rs256_key(platform_session):
    svc = KeyService(platform_session)
    key = await svc.generate_and_insert(audience="platform")
    await platform_session.flush()

    assert key.status == "active"
    assert key.algorithm == "RS256"
    assert key.audience == "platform"
    assert key.kid.startswith("platform-")
    assert "PUBLIC KEY" in key.public_key
    assert len(key.private_key_nonce) == 12
    assert len(key.private_key_tag) == 16


@pytest.mark.anyio
async def test_get_active_signing_key_returns_decrypted_pem(platform_session):
    svc = KeyService(platform_session)
    await svc.generate_and_insert(audience="platform")
    await platform_session.flush()

    kid, private_pem, algorithm = await svc.get_active_signing_key("platform")

    assert kid.startswith("platform-")
    assert b"PRIVATE KEY" in private_pem
    assert algorithm == "RS256"


@pytest.mark.anyio
async def test_get_active_signing_key_raises_when_no_key_exists(platform_session):
    svc = KeyService(platform_session)
    with pytest.raises(RuntimeError, match="No active signing key"):
        await svc.get_active_signing_key("platform")


@pytest.mark.anyio
async def test_get_verification_key_returns_public_pem_for_active_key(platform_session):
    svc = KeyService(platform_session)
    key = await svc.generate_and_insert(audience="platform")
    await platform_session.flush()

    public_pem, algorithm, audience = await svc.get_verification_key(key.kid)

    assert b"PUBLIC KEY" in public_pem
    assert algorithm == "RS256"
    assert audience == "platform"


@pytest.mark.anyio
async def test_get_verification_key_accepts_retiring_status(platform_session):
    svc = KeyService(platform_session)
    key = await svc.generate_and_insert(audience="platform")
    await platform_session.flush()
    key.status = "retiring"
    await platform_session.flush()

    public_pem, _, _ = await svc.get_verification_key(key.kid)
    assert b"PUBLIC KEY" in public_pem


@pytest.mark.anyio
async def test_get_verification_key_rejects_retired_key(platform_session):
    svc = KeyService(platform_session)
    key = await svc.generate_and_insert(audience="platform")
    await platform_session.flush()
    key.status = "retired"
    await platform_session.flush()

    with pytest.raises(ValueError, match="retired"):
        await svc.get_verification_key(key.kid)


@pytest.mark.anyio
async def test_get_verification_key_raises_for_unknown_kid(platform_session):
    svc = KeyService(platform_session)
    with pytest.raises(ValueError, match="Unknown kid"):
        await svc.get_verification_key("does-not-exist")


@pytest.mark.anyio
async def test_verify_boot_keys_passes_when_active_keys_exist(platform_session):
    svc = KeyService(platform_session)
    await svc.generate_and_insert(audience="platform")
    await svc.generate_and_insert(audience="tenant")
    await platform_session.flush()

    # Should not raise — both audiences have an active key.
    await verify_boot_keys(_override_session=platform_session)


@pytest.mark.anyio
async def test_verify_boot_keys_raises_when_platform_key_missing(platform_session):
    # Only tenant key exists — platform key missing.
    svc = KeyService(platform_session)
    await svc.generate_and_insert(audience="tenant")
    await platform_session.flush()

    with pytest.raises(RuntimeError, match="platform"):
        await verify_boot_keys(_override_session=platform_session)


@pytest.mark.anyio
async def test_verify_boot_keys_raises_when_no_keys_exist(platform_session):
    with pytest.raises(RuntimeError, match="No active JWT signing key"):
        await verify_boot_keys(_override_session=platform_session)
```

- [ ] **Step 2: Run new tests to confirm failure**

```bash
pytest tests/modules/iam/keys/test_key_service.py -v -k "not model_persists"
```

Expected: `ImportError` — `service.py` does not exist yet

- [ ] **Step 3: Create `app/modules/iam/keys/service.py`**

```python
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
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
            return cached  # type: ignore[return-value]

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
            return cached  # type: ignore[return-value]

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
```

- [ ] **Step 4: Run all key service tests to confirm pass**

```bash
pytest tests/modules/iam/keys/test_key_service.py -v
```

Expected: All tests PASS (model test + all new service tests)

- [ ] **Step 5: Commit**

```bash
git add app/modules/iam/keys/service.py tests/modules/iam/keys/test_key_service.py
git commit -m "feat(iam): KeyService — generate, get_active, get_verification, rotate, advance_lifecycle, verify_boot_keys"
```

---

### Task 6: KeyService — rotation and lifecycle advancement tests

**Files:**
- Modify: `tests/modules/iam/keys/test_key_service.py`

- [ ] **Step 1: Append rotation and lifecycle tests**

```python
# Append to tests/modules/iam/keys/test_key_service.py

@pytest.mark.anyio
async def test_rotate_promotes_new_key_and_demotes_current_to_retiring(platform_session):
    svc = KeyService(platform_session)
    original = await svc.generate_and_insert(audience="platform")
    await platform_session.flush()
    original_kid = original.kid

    new_key = await svc.rotate(audience="platform")
    await platform_session.flush()

    assert new_key.status == "active"
    assert new_key.kid != original_kid

    await platform_session.refresh(original)
    assert original.status == "retiring"


@pytest.mark.anyio
async def test_rotate_with_no_existing_key_creates_first_active_key(platform_session):
    svc = KeyService(platform_session)
    new_key = await svc.rotate(audience="tenant")
    await platform_session.flush()

    assert new_key.status == "active"
    assert new_key.audience == "tenant"


@pytest.mark.anyio
async def test_advance_lifecycle_retires_old_retiring_keys(platform_session):
    from datetime import timedelta

    svc = KeyService(platform_session)
    key = await svc.generate_and_insert(audience="platform")
    await platform_session.flush()

    key.status = "retiring"
    key.retired_at = datetime.now(UTC) - timedelta(hours=2)
    await platform_session.flush()

    counts = await svc.advance_lifecycle(datetime.now(UTC))
    await platform_session.flush()

    assert counts["retired"] == 1
    await platform_session.refresh(key)
    assert key.status == "retired"


@pytest.mark.anyio
async def test_advance_lifecycle_soft_deletes_aged_retired_keys(platform_session):
    from datetime import timedelta

    svc = KeyService(platform_session)
    key = await svc.generate_and_insert(audience="platform")
    await platform_session.flush()

    key.status = "retired"
    key.retired_at = datetime.now(UTC) - timedelta(days=8)
    await platform_session.flush()

    counts = await svc.advance_lifecycle(datetime.now(UTC))
    await platform_session.flush()

    assert counts["deleted"] == 1
    await platform_session.refresh(key)
    assert key.deleted_at is not None


@pytest.mark.anyio
async def test_advance_lifecycle_ignores_recently_retiring_keys(platform_session):
    from datetime import timedelta

    svc = KeyService(platform_session)
    key = await svc.generate_and_insert(audience="platform")
    await platform_session.flush()

    # Only 10 minutes old — should not be promoted to retired yet.
    key.status = "retiring"
    key.retired_at = datetime.now(UTC) - timedelta(minutes=10)
    await platform_session.flush()

    counts = await svc.advance_lifecycle(datetime.now(UTC))
    assert counts["retired"] == 0
    assert counts["deleted"] == 0
```

- [ ] **Step 2: Run all key service tests to confirm pass**

```bash
pytest tests/modules/iam/keys/test_key_service.py -v
```

Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/modules/iam/keys/test_key_service.py
git commit -m "test(iam): rotation and lifecycle advancement tests for KeyService"
```

---

### Task 7: TokenService — encode and decode

**Files:**
- Create: `app/modules/iam/tokens/service.py`
- Create: `tests/modules/iam/tokens/test_token_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/modules/iam/tokens/test_token_service.py
import uuid

import pytest

from app.modules.iam.tokens.service import (
    decode_token,
    encode_access_token,
    encode_refresh_token,
    get_unverified_kid,
)


def _make_rsa_keypair() -> tuple[bytes, bytes, str]:
    """Generate a test RSA keypair. Returns (private_pem, public_pem, kid)."""
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
    return private_pem, public_pem, "test-kid-001"


@pytest.fixture()
def rsa_keypair() -> tuple[bytes, bytes, str]:
    return _make_rsa_keypair()


def test_encode_access_token_produces_three_part_jwt(rsa_keypair):
    private_pem, _, kid = rsa_keypair
    token = encode_access_token(
        sub=str(uuid.uuid4()),
        audience="platform",
        session_id=str(uuid.uuid4()),
        actor_type="platform_user",
        kid=kid,
        private_key_pem=private_pem,
        algorithm="RS256",
        ttl_seconds=900,
    )
    assert isinstance(token, str)
    assert token.count(".") == 2


def test_decode_access_token_returns_all_expected_claims(rsa_keypair):
    private_pem, public_pem, kid = rsa_keypair
    subject = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    token = encode_access_token(
        sub=subject,
        audience="platform",
        session_id=session_id,
        actor_type="platform_user",
        kid=kid,
        private_key_pem=private_pem,
        algorithm="RS256",
        ttl_seconds=900,
    )
    claims = decode_token(
        token, audience="platform", public_key_pem=public_pem, algorithm="RS256"
    )

    assert claims["sub"] == subject
    assert claims["aud"] == "platform"
    assert claims["session_id"] == session_id
    assert claims["actor_type"] == "platform_user"
    assert claims["kid"] == kid
    assert "exp" in claims
    assert "iat" in claims
    assert "jti" in claims


def test_decode_token_with_wrong_audience_raises_value_error(rsa_keypair):
    private_pem, public_pem, kid = rsa_keypair
    token = encode_access_token(
        sub=str(uuid.uuid4()),
        audience="platform",
        session_id=str(uuid.uuid4()),
        actor_type="platform_user",
        kid=kid,
        private_key_pem=private_pem,
        algorithm="RS256",
        ttl_seconds=900,
    )
    with pytest.raises(ValueError, match="[Aa]udience"):
        decode_token(
            token, audience="tenant:acme", public_key_pem=public_pem, algorithm="RS256"
        )


def test_decode_expired_token_raises_value_error(rsa_keypair):
    private_pem, public_pem, kid = rsa_keypair
    token = encode_access_token(
        sub=str(uuid.uuid4()),
        audience="platform",
        session_id=str(uuid.uuid4()),
        actor_type="platform_user",
        kid=kid,
        private_key_pem=private_pem,
        algorithm="RS256",
        ttl_seconds=-1,  # already expired
    )
    with pytest.raises(ValueError, match="[Ee]xpir"):
        decode_token(
            token, audience="platform", public_key_pem=public_pem, algorithm="RS256"
        )


def test_decode_tampered_signature_raises_value_error(rsa_keypair):
    private_pem, public_pem, kid = rsa_keypair
    token = encode_access_token(
        sub=str(uuid.uuid4()),
        audience="platform",
        session_id=str(uuid.uuid4()),
        actor_type="platform_user",
        kid=kid,
        private_key_pem=private_pem,
        algorithm="RS256",
        ttl_seconds=900,
    )
    parts = token.split(".")
    tampered = parts[0] + "." + parts[1] + ".invalidsignatureXYZ"
    with pytest.raises(ValueError):
        decode_token(
            tampered, audience="platform", public_key_pem=public_pem, algorithm="RS256"
        )


def test_refresh_token_omits_actor_type_claim(rsa_keypair):
    import jwt as pyjwt

    private_pem, _, kid = rsa_keypair
    token = encode_refresh_token(
        sub=str(uuid.uuid4()),
        audience="platform",
        session_id=str(uuid.uuid4()),
        kid=kid,
        private_key_pem=private_pem,
        algorithm="RS256",
        ttl_seconds=3600,
    )
    payload = pyjwt.decode(token, options={"verify_signature": False}, algorithms=["RS256"])
    assert "sub" in payload
    assert "session_id" in payload
    assert "actor_type" not in payload


def test_each_token_gets_a_unique_jti(rsa_keypair):
    import jwt as pyjwt

    private_pem, _, kid = rsa_keypair
    tokens = [
        encode_access_token(
            sub=str(uuid.uuid4()),
            audience="platform",
            session_id=str(uuid.uuid4()),
            actor_type="platform_user",
            kid=kid,
            private_key_pem=private_pem,
            algorithm="RS256",
            ttl_seconds=900,
        )
        for _ in range(3)
    ]
    jtis = [
        pyjwt.decode(t, options={"verify_signature": False}, algorithms=["RS256"])["jti"]
        for t in tokens
    ]
    assert len(set(jtis)) == 3  # all unique


def test_get_unverified_kid_extracts_kid_from_header(rsa_keypair):
    private_pem, _, kid = rsa_keypair
    token = encode_access_token(
        sub=str(uuid.uuid4()),
        audience="platform",
        session_id=str(uuid.uuid4()),
        actor_type="platform_user",
        kid=kid,
        private_key_pem=private_pem,
        algorithm="RS256",
        ttl_seconds=900,
    )
    assert get_unverified_kid(token) == kid


def test_get_unverified_kid_raises_on_malformed_token():
    with pytest.raises(ValueError, match="Malformed"):
        get_unverified_kid("not.a.jwt")
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/iam/tokens/test_token_service.py -v
```

Expected: `ImportError` — `tokens/service.py` does not exist yet

- [ ] **Step 3: Install PyJWT if not already present**

```bash
pip install "PyJWT>=2.8"
```

Confirm `PyJWT` (not `jwt` from another package) is installed:

```bash
python -c "import jwt; print(jwt.__version__)"
```

Expected: version string ≥ 2.8.0

- [ ] **Step 4: Create `app/modules/iam/tokens/service.py`**

```python
"""JWT encode/decode using PyJWT (RS256 or EdDSA).

Token claims:
    sub         — subject (user UUID string)
    aud         — audience: "platform" or "tenant:<slug>"
    iat         — issued-at (UTC epoch seconds; set automatically by PyJWT)
    exp         — expiry (UTC epoch seconds)
    jti         — unique token ID (UUID4 string); used for refresh-token revocation
    kid         — key ID placed in the JWT *header* (not payload); used to select the key
    actor_type  — "platform_user" or "tenant_user" (access tokens only)
    session_id  — server-side session row UUID (both access and refresh tokens)

Refresh tokens omit ``actor_type`` — they are only used to issue new access tokens,
not to authorise resource access.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import structlog

_log = structlog.get_logger(__name__)


def encode_access_token(
    *,
    sub: str,
    audience: str,
    session_id: str,
    actor_type: str,
    kid: str,
    private_key_pem: bytes,
    algorithm: str,
    ttl_seconds: int,
) -> str:
    """Issue a signed access token.

    Args:
        sub: Subject (user UUID as string).
        audience: JWT ``aud`` claim — "platform" or "tenant:<slug>".
        session_id: Server-side session UUID; used to revoke on logout.
        actor_type: "platform_user" or "tenant_user".
        kid: Key ID placed in the JWT header for key selection by verifiers.
        private_key_pem: PKCS8 PEM bytes of the RS256 or EdDSA private key.
        algorithm: "RS256" or "EdDSA".
        ttl_seconds: Token lifetime. Pass a negative value in tests to produce
            an already-expired token.
    """
    now = datetime.now(UTC)
    payload: dict = {
        "sub": sub,
        "aud": audience,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
        "jti": str(uuid.uuid4()),
        "actor_type": actor_type,
        "session_id": session_id,
    }
    return pyjwt.encode(
        payload,
        private_key_pem,
        algorithm=algorithm,
        headers={"kid": kid},
    )


def encode_refresh_token(
    *,
    sub: str,
    audience: str,
    session_id: str,
    kid: str,
    private_key_pem: bytes,
    algorithm: str,
    ttl_seconds: int,
) -> str:
    """Issue a signed refresh token.

    Refresh tokens are minimal — they carry ``sub``, ``aud``, ``iat``, ``exp``,
    ``jti``, and ``session_id``. They deliberately omit ``actor_type`` and other
    identity claims: they are only used to obtain new access tokens, not to
    authorise resource access directly.
    """
    now = datetime.now(UTC)
    payload: dict = {
        "sub": sub,
        "aud": audience,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
        "jti": str(uuid.uuid4()),
        "session_id": session_id,
    }
    return pyjwt.encode(
        payload,
        private_key_pem,
        algorithm=algorithm,
        headers={"kid": kid},
    )


def get_unverified_kid(token: str) -> str:
    """Extract the ``kid`` from the JWT header without verifying the signature.

    Called before ``decode_token`` to select the correct public key.

    Raises ``ValueError`` if the token is malformed or has no ``kid`` header.
    """
    try:
        header = pyjwt.get_unverified_header(token)
    except pyjwt.exceptions.DecodeError as exc:
        raise ValueError(f"Malformed JWT header: {exc}") from exc
    kid = header.get("kid")
    if not kid:
        raise ValueError("JWT header is missing required 'kid' field")
    return kid


def decode_token(
    token: str,
    *,
    audience: str,
    public_key_pem: bytes,
    algorithm: str,
) -> dict:
    """Verify and decode a JWT, returning the claims dict.

    Validates: signature, expiry (``exp``), and audience (``aud``).

    Also adds ``kid`` from the header into the returned claims dict so callers
    do not need a second header parse.

    Raises ``ValueError`` for any validation failure — expired token, audience
    mismatch, bad signature, or malformed token.
    """
    try:
        claims: dict = pyjwt.decode(
            token,
            public_key_pem,
            algorithms=[algorithm],
            audience=audience,
        )
    except pyjwt.exceptions.ExpiredSignatureError as exc:
        raise ValueError("Token has expired") from exc
    except pyjwt.exceptions.InvalidAudienceError as exc:
        raise ValueError(f"Audience mismatch: expected '{audience}'") from exc
    except pyjwt.exceptions.DecodeError as exc:
        raise ValueError(f"Token decode failed: {exc}") from exc
    except pyjwt.exceptions.PyJWTError as exc:
        raise ValueError(f"JWT validation failed: {exc}") from exc

    # Propagate kid from the header into the claims dict.
    try:
        header = pyjwt.get_unverified_header(token)
        claims["kid"] = header.get("kid", "")
    except pyjwt.exceptions.DecodeError:
        pass  # already validated above; this re-read is best-effort

    return claims
```

- [ ] **Step 5: Run all token service tests to confirm pass**

```bash
pytest tests/modules/iam/tokens/test_token_service.py -v
```

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/modules/iam/tokens/service.py tests/modules/iam/tokens/test_token_service.py
git commit -m "feat(iam): TokenService — encode_access_token, encode_refresh_token, decode_token (PyJWT RS256)"
```

---

### Task 8: Key schemas, JWKS endpoint, and admin list endpoint

**Files:**
- Create: `app/modules/iam/keys/schemas.py`
- Create: `app/modules/iam/keys/api.py`
- Modify: `app/main.py` — include `jwks_router` and `key_mgmt_router`

- [ ] **Step 1: Write the failing tests**

```python
# tests/modules/iam/keys/test_key_api.py
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.modules.iam.keys.service import clear_key_caches


@pytest.fixture(autouse=True)
def reset_caches():
    clear_key_caches()
    yield
    clear_key_caches()


@pytest.mark.anyio
async def test_jwks_endpoint_is_reachable_and_returns_keys_list():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/.well-known/jwks.json")
    assert response.status_code == 200
    body = response.json()
    assert "keys" in body
    assert isinstance(body["keys"], list)


@pytest.mark.anyio
async def test_jwks_endpoint_requires_no_auth_header():
    # No Authorization or X-Platform-Actor-ID — must not return 401 or 403.
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/.well-known/jwks.json")
    assert response.status_code not in (401, 403)


@pytest.mark.anyio
async def test_platform_jwt_keys_list_rejects_non_uuid_actor_id():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/platform/jwt-keys/",
            headers={"X-Platform-Actor-ID": "not-a-uuid"},
        )
    assert response.status_code in (400, 422)


@pytest.mark.anyio
async def test_platform_jwt_keys_list_rejects_missing_actor_id():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/platform/jwt-keys/")
    assert response.status_code == 422  # missing required header
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/iam/keys/test_key_api.py -v
```

Expected: `ImportError` or 404 — routes do not exist yet

- [ ] **Step 3: Create `app/modules/iam/keys/schemas.py`**

```python
"""Pydantic schemas for JWT key management responses."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class JwkOut(BaseModel):
    """Single RSA public key in JWK format."""

    kty: str = "RSA"
    kid: str
    use: str = "sig"
    alg: str
    n: str  # RSA modulus, base64url-encoded
    e: str  # RSA public exponent, base64url-encoded


class JwksResponse(BaseModel):
    """JWK Set — returned by GET /.well-known/jwks.json."""

    keys: list[JwkOut]


class JwtKeyOut(BaseModel):
    """Admin view of a signing key row. No private key material."""

    id: uuid.UUID
    kid: str
    algorithm: str
    audience: str
    status: str
    created_at: datetime
    activated_at: datetime | None
    retired_at: datetime | None
    deleted_at: datetime | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Create `app/modules/iam/keys/api.py`**

```python
"""JWT key management API.

Public (no auth):
    GET  /.well-known/jwks.json   — JWK Set for external token verification

Superuser-only (platform auth dependency):
    GET  /platform/jwt-keys/       — list all non-deleted signing keys
"""
from __future__ import annotations

import base64

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_platform_session
from app.modules.iam.keys.models import JwtSigningKey
from app.modules.iam.keys.schemas import JwtKeyOut, JwkOut, JwksResponse

_log = structlog.get_logger(__name__)

# Public — mounted at app root so the path is exactly /.well-known/jwks.json.
jwks_router = APIRouter(tags=["jwks"])

# Superuser admin endpoints.
key_mgmt_router = APIRouter(prefix="/platform/jwt-keys", tags=["platform-jwt-keys"])


def _rsa_pem_to_jwk(kid: str, public_key_pem: str, algorithm: str) -> JwkOut:
    """Convert an RSA public key PEM to a JWK dict."""
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    key = load_pem_public_key(public_key_pem.encode())
    numbers = key.public_key().public_numbers()  # type: ignore[attr-defined]
    key_size_bytes = (key.key_size + 7) // 8  # type: ignore[attr-defined]

    def _b64url(n: int, byte_length: int) -> str:
        return (
            base64.urlsafe_b64encode(n.to_bytes(byte_length, "big"))
            .rstrip(b"=")
            .decode()
        )

    return JwkOut(
        kid=kid,
        alg=algorithm,
        n=_b64url(numbers.n, key_size_bytes),
        e=_b64url(numbers.e, 3),
    )


@jwks_router.get("/.well-known/jwks.json", response_model=JwksResponse)
async def get_jwks(
    session: AsyncSession = Depends(get_platform_session),
) -> JwksResponse:
    """Return active and retiring public keys in JWK Set format.

    Public endpoint — no authentication required.
    Returns an empty ``keys`` list when no signing keys exist yet.
    """
    result = await session.execute(
        select(JwtSigningKey)
        .where(JwtSigningKey.status.in_(["active", "retiring"]))
        .where(JwtSigningKey.deleted_at.is_(None))
        .order_by(JwtSigningKey.created_at.desc())
    )
    keys = result.scalars().all()

    jwks: list[JwkOut] = []
    for key in keys:
        if key.algorithm == "RS256":
            jwks.append(_rsa_pem_to_jwk(key.kid, key.public_key, key.algorithm))
        # EdDSA support: add here in a future plan when EdDSA keys are introduced.

    return JwksResponse(keys=jwks)


@key_mgmt_router.get("/", response_model=list[JwtKeyOut])
async def list_jwt_keys(
    session: AsyncSession = Depends(get_platform_session),
) -> list[JwtKeyOut]:
    """List all non-deleted signing keys. Requires superuser.

    When ``PLATFORM_AUTH_MODE`` is flipped to ``jwt`` in plan 09, the
    ``get_current_superuser`` dependency will enforce real JWT verification.
    Until then the stub enforces UUID validity and active status.
    """
    from app.platform_.auth import get_current_superuser
    from app.platform_.models import PlatformUser

    # Enforce superuser via the platform auth dependency.
    # Declared here (not in the function signature) so ruff does not complain
    # about an unused import when the dependency is used only for its side effects.
    # In practice, call this endpoint through the router which passes the
    # dependency — see the note in main.py about the router-level dependency.
    result = await session.execute(
        select(JwtSigningKey)
        .where(JwtSigningKey.deleted_at.is_(None))
        .order_by(JwtSigningKey.created_at.desc())
    )
    signing_keys = result.scalars().all()
    return [JwtKeyOut.model_validate(k) for k in signing_keys]
```

> **Note on auth for `/platform/jwt-keys/`:** The list endpoint currently has no
> enforced auth (the stub reads `X-Platform-Actor-ID`). To enforce superuser, wire
> `get_current_superuser` as a router-level dependency in `app/main.py` when
> including `key_mgmt_router`. This is done in the next step.

- [ ] **Step 5: Add router includes and boot check to `app/main.py`**

Add imports after the existing platform router imports (around line 16):

```python
from app.modules.iam.keys.api import jwks_router, key_mgmt_router
from app.platform_.auth import get_current_superuser
```

Replace the existing lifespan function body:

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=False)

    # Refuse stub auth in production.
    if settings.app_env == "production" and settings.platform_auth_mode == "stub":
        raise RuntimeError(
            "Refusing to boot: PLATFORM_AUTH_MODE=stub is forbidden in production. "
            "Set PLATFORM_AUTH_MODE=jwt when IAM ships."
        )

    # Verify active signing keys exist when JWT auth is enabled.
    if settings.platform_auth_mode == "jwt":
        from app.modules.iam.keys.service import verify_boot_keys
        await verify_boot_keys()

    _log.info("Startup complete", env=settings.app_env)
    yield
    await app.state.redis.aclose()
    await engine.dispose()
    _log.info("Shutdown complete")
```

Add the two new router includes after the existing `app.include_router` calls:

```python
app.include_router(jwks_router)
app.include_router(
    key_mgmt_router,
    dependencies=[Depends(get_current_superuser)],
)
```

Add `Depends` to the FastAPI import at the top if not already present:

```python
from fastapi import Depends, FastAPI, Request
```

- [ ] **Step 6: Run tests to confirm pass**

```bash
pytest tests/modules/iam/keys/test_key_api.py -v
```

Expected: All tests PASS

- [ ] **Step 7: Run full IAM key suite to confirm no regressions**

```bash
pytest tests/modules/iam/ -v
```

Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add app/modules/iam/keys/schemas.py app/modules/iam/keys/api.py app/main.py
git add tests/modules/iam/keys/test_key_api.py
git commit -m "feat(iam): JWKS endpoint + key management API; wire boot check into lifespan"
```

---

### Task 9: Celery beat tasks — advance_key_lifecycle, rotate_signing_keys_if_due

**Files:**
- Create: `app/modules/iam/beat.py`
- Modify: `app/workers/celery_app.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/modules/iam/test_beat.py
import pytest


def test_beat_module_imports_without_error():
    """Smoke test — verify the beat module loads and exposes the expected task names."""
    import app.modules.iam.beat as beat_module

    assert hasattr(beat_module, "advance_key_lifecycle")
    assert hasattr(beat_module, "rotate_signing_keys_if_due")


def test_advance_key_lifecycle_is_registered_celery_task():
    from app.modules.iam.beat import advance_key_lifecycle
    from app.workers.celery_app import celery_app

    assert "app.modules.iam.beat.advance_key_lifecycle" in celery_app.tasks


def test_rotate_signing_keys_if_due_is_registered_celery_task():
    from app.modules.iam.beat import rotate_signing_keys_if_due
    from app.workers.celery_app import celery_app

    assert "app.modules.iam.beat.rotate_signing_keys_if_due" in celery_app.tasks
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/iam/test_beat.py -v
```

Expected: `ImportError` — `beat.py` does not exist yet; `celery_app.tasks` does not contain iam entries

- [ ] **Step 3: Create `app/modules/iam/beat.py`**

```python
"""Celery beat tasks for JWT signing key lifecycle management.

Tasks run in a synchronous Celery worker context. They bridge into async
code using ``asyncio.run()`` — the same pattern as the outbox relay workers.
A fresh SQLAlchemy engine is created per task invocation (matches the outbox
worker pattern) to avoid connection-pool sharing across Celery processes.
"""
from __future__ import annotations

import asyncio
import structlog
from datetime import UTC, datetime

from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)


async def _run_advance_lifecycle() -> dict:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from app.modules.iam.keys.service import KeyService

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            await session.execute(text("SET LOCAL search_path TO platform"))
            svc = KeyService(session)
            now = datetime.now(UTC)
            counts = await svc.advance_lifecycle(now)
            await session.commit()
            _log.info("iam.key_lifecycle_advanced", **counts)
            return counts
    finally:
        await engine.dispose()


async def _run_rotate_if_due() -> dict[str, list[str]]:
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from app.modules.iam.keys.models import JwtSigningKey
    from app.modules.iam.keys.service import KeyService

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    rotated: list[str] = []
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            await session.execute(text("SET LOCAL search_path TO platform"))
            svc = KeyService(session)

            from datetime import timedelta

            rotation_threshold = datetime.now(UTC) - timedelta(
                days=settings.jwt_key_rotation_days
            )

            for audience in ("platform", "tenant"):
                result = await session.execute(
                    select(JwtSigningKey)
                    .where(JwtSigningKey.audience == audience)
                    .where(JwtSigningKey.status == "active")
                )
                active_key = result.scalar_one_or_none()

                if active_key is None:
                    # No active key — skip; verify_boot_keys will catch this at next startup.
                    _log.warning("iam.beat.no_active_key_for_rotation", audience=audience)
                    continue

                if active_key.activated_at and active_key.activated_at <= rotation_threshold:
                    new_key = await svc.rotate(audience=audience)
                    await session.commit()
                    rotated.append(audience)
                    _log.info(
                        "iam.beat.key_rotated",
                        audience=audience,
                        new_kid=new_key.kid,
                    )

        return {"rotated": rotated}
    finally:
        await engine.dispose()


@celery_app.task(name="app.modules.iam.beat.advance_key_lifecycle")  # type: ignore[misc]
def advance_key_lifecycle() -> dict:
    """Hourly: advance retiring→retired; soft-delete aged retired keys."""
    return asyncio.run(_run_advance_lifecycle())


@celery_app.task(name="app.modules.iam.beat.rotate_signing_keys_if_due")  # type: ignore[misc]
def rotate_signing_keys_if_due() -> dict:
    """Daily: rotate the active key for each audience if it has exceeded JWT_KEY_ROTATION_DAYS."""
    return asyncio.run(_run_rotate_if_due())
```

- [ ] **Step 4: Update `app/workers/celery_app.py` to include the IAM beat module**

Add `"app.modules.iam.beat"` to the `include` list:

```python
celery_app = Celery(
    "sacco",
    broker=settings.redis_url,
    include=[
        "app.core.outbox.worker",
        "app.core.outbox.retention",
        "app.platform_.provisioning.tasks",
        "app.modules.iam.beat",
    ],
)
```

Add the beat schedule entries inside `celery_app.conf.update(...)`:

```python
"advance-jwt-key-lifecycle": {
    "task": "app.modules.iam.beat.advance_key_lifecycle",
    "schedule": 3600.0,  # hourly
},
"rotate-jwt-keys-if-due": {
    "task": "app.modules.iam.beat.rotate_signing_keys_if_due",
    "schedule": 24 * 3600.0,  # daily
},
```

- [ ] **Step 5: Run beat tests to confirm pass**

```bash
pytest tests/modules/iam/test_beat.py -v
```

Expected: All tests PASS

- [ ] **Step 6: Run full IAM test suite to confirm no regressions**

```bash
pytest tests/modules/iam/ -v
```

Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add app/modules/iam/beat.py app/workers/celery_app.py tests/modules/iam/test_beat.py
git commit -m "feat(iam): Celery beat tasks — advance_key_lifecycle (hourly), rotate_signing_keys_if_due (daily)"
```

---

## Verification Criteria

Before marking this plan complete, run the following:

```bash
# 1. Linting
ruff check app/modules/iam/ app/core/config.py app/main.py app/workers/celery_app.py

# 2. Type checking
mypy app/modules/iam/ app/core/config.py app/main.py --strict

# 3. IAM-specific tests
pytest tests/modules/iam/ -v

# 4. Regression: full suite
pytest tests/ -v

# 5. Spot-check migration syntax
python -c "
import importlib.util
spec = importlib.util.spec_from_file_location('m003', 'alembic/platform/versions/003_iam_platform.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
assert m.revision == '003'
assert m.down_revision == '002'
print('Migration 003 OK')
"
```

All commands must exit cleanly (zero errors, all tests green) before this plan is considered complete.

---

## What is NOT in this plan

The following are deliberately deferred to their respective sub-plans:

- `platform.platform_sessions` table and `SessionService` → **Plan 03**
- `tenant_sessions` and `tenant_users` tables → **Plans 03 and 04**
- `PlatformAuthService`, `/platform/auth/token` endpoint → **Plan 05**
- `TenantAuthService`, `/auth/token` endpoint → **Plan 06**
- Password hashing (`argon2id`) → **Plan 02**
- Real `get_current_platform_user` JWT implementation → **Plan 09**
- Account lockout → **Plan 10**
- Auth audit events → **Plan 11**
- Flipping `PLATFORM_AUTH_MODE` default to `jwt` → **Plan 12**
