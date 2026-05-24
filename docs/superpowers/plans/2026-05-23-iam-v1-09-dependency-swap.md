# IAM v1-09: Dependency Swap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stub `get_current_platform_user` in `app/platform_/auth.py` with a real JWT-validating implementation when `PLATFORM_AUTH_MODE=jwt`, and introduce `get_current_tenant_user` (both stub and JWT variants) bound by a new `TENANT_AUTH_MODE` setting. All existing callers (`CurrentPlatformUser`, `CurrentTenantUser` `Depends` in route handlers) continue to work unchanged — the binding switch is invisible to routers.

**Architecture:** A new `app/modules/iam/dependencies.py` module defines the real JWT implementations of both user dependencies. The binding switch runs at module import time in each binding file: `app/platform_/auth.py` chooses between its existing stub and the new JWT function based on `platform_auth_mode`; `dependencies.py` exports `get_current_tenant_user` and `CurrentTenantUser` bound the same way for `tenant_auth_mode`. Because `tests/conftest.py` sets `PLATFORM_AUTH_MODE=stub` and (after this plan) `TENANT_AUTH_MODE=stub` as environment defaults, all existing tests continue to pass without change. The JWT path is exercised by targeted unit tests that call the dependency functions directly with mocked inputs.

**Tech Stack:** FastAPI `Depends`, PyJWT, SQLAlchemy 2.0 async, pydantic-settings

---

## Required Reading (complete before starting any task)

1. `CLAUDE.md` — architectural rules
2. `docs/superpowers/specs/2026-05-21-iam-v1-design.md` §8 — dependency implementations
3. `app/platform_/auth.py` — existing stub; full body must be preserved in the else-branch
4. `app/core/config.py` — `Settings` class (add `tenant_auth_mode` here)
5. `app/core/db.py` — `get_platform_session`, `get_tenant_session` (dependency signatures)
6. `app/modules/iam/keys/service.py` — `KeyService(db=session)` (Plan 01)
7. `app/modules/iam/sessions/service.py` — `SessionService(db, model_cls, redis)` (Plan 03)
8. `app/modules/iam/sessions/models.py` — `PlatformSession`, `TenantSession` (Plan 03)
9. `app/modules/iam/tokens/service.py` — `decode_token(token, audience, key_service)` (Plan 01)
10. `app/modules/iam/tenant_users/models.py` — `TenantUser` (Plan 04)
11. `app/platform_/models.py` — `PlatformUser`
12. `tests/conftest.py` — note the `os.environ.setdefault("PLATFORM_AUTH_MODE", "stub")` line

---

## Binding Order Invariant

Every binding file must respect this order:

1. Define or import both candidate functions (stub and jwt)
2. Run the `if/else` to assign `get_current_*_user`
3. Define `Current*User = Annotated[..., Depends(get_current_*_user)]`
4. Define any functions that use `Current*User` as a parameter type

Python evaluates module-level code top-to-bottom at import time, so as long as this order is preserved, the `Depends(...)` call captures the correct function reference.

---

## File Map

```
MODIFY app/core/config.py                         — add tenant_auth_mode setting
MODIFY tests/conftest.py                          — setdefault TENANT_AUTH_MODE=stub
MODIFY tests/core/test_config.py                  — add tenant_auth_mode tests
CREATE app/modules/iam/dependencies.py            — JWT impls + tenant stub + CurrentTenantUser binding
MODIFY app/platform_/auth.py                      — import-time binding switch for platform
MODIFY app/main.py                                — TENANT_AUTH_MODE boot check
CREATE tests/modules/iam/test_dependencies.py     — unit tests for JWT dependency functions
```

---

### Task 1: `tenant_auth_mode` configuration setting

**Files:**
- Modify: `app/core/config.py`
- Modify: `tests/conftest.py`
- Modify: `tests/core/test_config.py`

- [ ] **Step 1: Write the failing config tests**

Append to `tests/core/test_config.py`:

```python
def test_tenant_auth_mode_defaults_to_stub():
    from app.core.config import Settings

    s = Settings(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        app_secret_key="x",
    )
    assert s.tenant_auth_mode == "stub"


def test_tenant_auth_mode_is_configurable():
    from app.core.config import Settings

    s = Settings(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        app_secret_key="x",
        tenant_auth_mode="jwt",
    )
    assert s.tenant_auth_mode == "jwt"
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/core/test_config.py -v -k "tenant_auth_mode"
```

Expected: `ValidationError` or `AttributeError` — field does not exist yet

- [ ] **Step 3: Add `tenant_auth_mode` to `app/core/config.py`**

In the `Settings` class body, add after the `platform_bootstrap_full_name` line or after the existing `platform_auth_mode` block (whichever is present after Plan 01 additions):

```python
    # Tenant auth
    tenant_auth_mode: str = "stub"  # "stub" | "jwt"
```

After the edit, the relevant section should look like:

```python
    # Platform auth
    platform_auth_mode: str = "stub"  # "stub" | "jwt"
    platform_bootstrap_email: str = ""
    platform_bootstrap_full_name: str = "Platform Admin"

    # Tenant auth
    tenant_auth_mode: str = "stub"  # "stub" | "jwt"
```

> If Plan 01 already added `tenant_auth_mode` as part of its JWT settings block, skip this step and just confirm the field exists and defaults to `"stub"`.

- [ ] **Step 4: Add `TENANT_AUTH_MODE=stub` to `tests/conftest.py`**

Add this line alongside the existing `os.environ.setdefault` calls near the top of `tests/conftest.py`:

```python
os.environ.setdefault("TENANT_AUTH_MODE", "stub")
```

The relevant block after the edit:

```python
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-not-used-in-production")
os.environ.setdefault("PLATFORM_BOOTSTRAP_EMAIL", "admin@test.example")
os.environ.setdefault("PLATFORM_AUTH_MODE", "stub")
os.environ.setdefault("TENANT_AUTH_MODE", "stub")
```

- [ ] **Step 5: Run config tests to confirm pass**

```bash
pytest tests/core/test_config.py -v -k "tenant_auth_mode"
```

Expected: 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/core/config.py tests/core/test_config.py tests/conftest.py
git commit -m "feat(iam): add tenant_auth_mode config setting (default stub)"
```

---

### Task 2: `app/modules/iam/dependencies.py` — JWT implementations and binding

**Files:**
- Create: `app/modules/iam/dependencies.py`

This file contains:
- `get_current_platform_user_jwt` — real platform JWT dependency
- `get_current_tenant_user_stub` — tenant stub (mirrors platform stub pattern)
- `get_current_tenant_user_jwt` — real tenant JWT dependency
- Module-level binding switch → `get_current_tenant_user`
- `CurrentTenantUser` type alias

The platform binding lives in `app/platform_/auth.py` (Task 3). Only the JWT function is defined here.

- [ ] **Step 1: Create `app/modules/iam/dependencies.py`**

```python
"""Real JWT-validating FastAPI dependencies for platform and tenant users.

Platform dependency (get_current_platform_user_jwt):
    Imported by app/platform_/auth.py when PLATFORM_AUTH_MODE=jwt.
    Callers continue to use CurrentPlatformUser from app/platform_/auth.py
    — no call-site changes needed.

Tenant dependency (get_current_tenant_user / CurrentTenantUser):
    Exported directly from this module. Tenant route handlers import
    CurrentTenantUser here:
        from app.modules.iam.dependencies import CurrentTenantUser

Binding switch:
    PLATFORM_AUTH_MODE controls which platform function is active (done in
    app/platform_/auth.py, not here).
    TENANT_AUTH_MODE controls which tenant function is active (done here,
    at module import time).

Test safety:
    tests/conftest.py sets PLATFORM_AUTH_MODE=stub and TENANT_AUTH_MODE=stub
    via os.environ.setdefault BEFORE any module imports, so the binding
    resolves to the stub in all existing tests.
"""
from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_platform_session, get_tenant_session
from app.modules.iam.keys.service import KeyService
from app.modules.iam.sessions.models import PlatformSession, TenantSession
from app.modules.iam.sessions.service import SessionService
from app.modules.iam.tenant_users.models import TenantUser
from app.modules.iam.tokens.service import decode_token
from app.platform_.models import PlatformUser

_log = structlog.get_logger(__name__)
_bearer = HTTPBearer()

# ── Platform JWT implementation ───────────────────────────────────────────────


async def get_current_platform_user_jwt(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_platform_session)],
    request: Request,
) -> PlatformUser:
    """Real platform auth dependency: validates Bearer JWT, checks session.

    Imported by app/platform_/auth.py when PLATFORM_AUTH_MODE=jwt.
    Returns the same PlatformUser type as the stub — callers are unaffected.
    """
    redis = getattr(request.app.state, "redis", None)
    key_service = KeyService(db=session)

    try:
        claims = await decode_token(
            token=credentials.credentials,
            audience="platform",
            key_service=key_service,
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    session_id_str = claims.get("session_id")
    sub = claims.get("sub")
    if not session_id_str or not sub:
        raise HTTPException(status_code=401, detail="Malformed token claims")

    try:
        session_id = uuid.UUID(session_id_str)
        user_id = uuid.UUID(sub)
    except ValueError:
        raise HTTPException(status_code=401, detail="Malformed token claims")

    svc = SessionService(db=session, model_cls=PlatformSession, redis=redis)
    session_row = await svc.get_by_session_id(session_id)
    if session_row is None or session_row.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Session not found or revoked")

    result = await session.execute(
        select(PlatformUser).where(PlatformUser.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    structlog.contextvars.bind_contextvars(
        actor_type="platform_user",
        actor_id=str(user.id),
        actor_label=user.email,
    )

    return user


# ── Tenant stub ───────────────────────────────────────────────────────────────


async def get_current_tenant_user_stub(
    x_tenant_actor_id: Annotated[str, Header(alias="X-Tenant-Actor-ID")],
    session: Annotated[AsyncSession, Depends(get_tenant_session)],
) -> TenantUser:
    """Stub: validates X-Tenant-Actor-ID against tenant_users. NOT production auth.

    Emits a WARNING on every call. Active when TENANT_AUTH_MODE=stub (default).
    Does NOT verify the caller is who the header claims.
    """
    _log.warning(
        "TENANT STUB AUTH: actor_id=%s — not production auth",
        x_tenant_actor_id,
    )

    try:
        actor_id = uuid.UUID(x_tenant_actor_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid X-Tenant-Actor-ID: must be a UUID",
        ) from exc

    result = await session.execute(
        select(TenantUser).where(TenantUser.id == actor_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=401, detail="Tenant actor not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Tenant actor is inactive")

    structlog.contextvars.bind_contextvars(
        actor_type="tenant_user",
        actor_id=str(user.id),
        actor_label=user.email,
    )

    return user


# ── Tenant JWT implementation ─────────────────────────────────────────────────


async def get_current_tenant_user_jwt(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    tenant_db: Annotated[AsyncSession, Depends(get_tenant_session)],
    platform_db: Annotated[AsyncSession, Depends(get_platform_session)],
    request: Request,
) -> TenantUser:
    """Real tenant auth dependency: validates Bearer JWT, checks session.

    Two sessions are injected: tenant_db for TenantUser / TenantSession
    lookups; platform_db for KeyService (reads platform.jwt_signing_keys).

    The JWT audience is "tenant:<slug>" where slug comes from X-Tenant-Slug.
    get_tenant_session has already validated the slug — we re-read it here
    for the audience claim only.
    """
    settings = get_settings()
    tenant_slug = request.headers.get(settings.tenant_header, "")
    redis = getattr(request.app.state, "redis", None)

    key_service = KeyService(db=platform_db)
    audience = f"tenant:{tenant_slug}"

    try:
        claims = await decode_token(
            token=credentials.credentials,
            audience=audience,
            key_service=key_service,
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    session_id_str = claims.get("session_id")
    sub = claims.get("sub")
    if not session_id_str or not sub:
        raise HTTPException(status_code=401, detail="Malformed token claims")

    try:
        session_id = uuid.UUID(session_id_str)
        user_id = uuid.UUID(sub)
    except ValueError:
        raise HTTPException(status_code=401, detail="Malformed token claims")

    svc = SessionService(db=tenant_db, model_cls=TenantSession, redis=redis)
    session_row = await svc.get_by_session_id(session_id)
    if session_row is None or session_row.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Session not found or revoked")

    result = await tenant_db.execute(
        select(TenantUser).where(TenantUser.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    structlog.contextvars.bind_contextvars(
        actor_type="tenant_user",
        actor_id=str(user.id),
        actor_label=user.email,
    )

    return user


# ── Tenant binding switch (runs at import time) ───────────────────────────────

_settings = get_settings()

if _settings.tenant_auth_mode == "jwt":
    get_current_tenant_user = get_current_tenant_user_jwt
else:
    get_current_tenant_user = get_current_tenant_user_stub

CurrentTenantUser = Annotated[TenantUser, Depends(get_current_tenant_user)]
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
python -c "
from app.modules.iam.dependencies import (
    get_current_platform_user_jwt,
    get_current_tenant_user_stub,
    get_current_tenant_user_jwt,
    get_current_tenant_user,
    CurrentTenantUser,
)
print('dependencies module OK')
print('tenant binding:', get_current_tenant_user.__name__)
"
```

Expected output (default env `TENANT_AUTH_MODE=stub`):
```
dependencies module OK
tenant binding: get_current_tenant_user_stub
```

- [ ] **Step 3: Commit**

```bash
git add app/modules/iam/dependencies.py
git commit -m "feat(iam): JWT dependency implementations + CurrentTenantUser binding"
```

---

### Task 3: Platform binding switch in `app/platform_/auth.py`

**Files:**
- Modify: `app/platform_/auth.py`

The existing stub body is preserved verbatim in the `else` branch. Only the module structure changes (adding the `if/else` switch). **Do not change any function signatures or logic inside the stub.**

- [ ] **Step 1: Rewrite `app/platform_/auth.py` with the binding switch**

The complete new content of `app/platform_/auth.py`:

```python
"""Platform authentication dependency — stub or JWT depending on PLATFORM_AUTH_MODE.

When PLATFORM_AUTH_MODE=stub (default):
    get_current_platform_user validates X-Platform-Actor-ID against
    platform.platform_users but does NOT authenticate. Replace internals
    with JWT decode when IAM ships — the dependency signature stays unchanged.

When PLATFORM_AUTH_MODE=jwt:
    get_current_platform_user validates a Bearer JWT, checks session
    non-revocation, and returns the PlatformUser. Provided by
    app/modules/iam/dependencies.get_current_platform_user_jwt.

Production boot guard: APP_ENV=production + PLATFORM_AUTH_MODE=stub → crash.
"""
from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_platform_session
from app.platform_.models import PlatformUser

_log = structlog.get_logger(__name__)

PlatformSession = Annotated[AsyncSession, Depends(get_platform_session)]
ActorHeader = Annotated[str, Header(alias="X-Platform-Actor-ID")]

# ── Binding switch (runs at import time) ──────────────────────────────────────

_settings = get_settings()

if _settings.platform_auth_mode == "jwt":
    from app.modules.iam.dependencies import (
        get_current_platform_user_jwt as get_current_platform_user,
    )
else:
    async def get_current_platform_user(  # type: ignore[misc]
        x_platform_actor_id: ActorHeader,
        session: PlatformSession,
    ) -> PlatformUser:
        """Stub: parse X-Platform-Actor-ID, validate it exists and is active.

        Emits a WARNING on every call — this is intentional and noisy.
        Does NOT prove the caller is who the header claims.
        """
        _log.warning(
            "PLATFORM STUB AUTH: actor_id=%s — not production auth",
            x_platform_actor_id,
        )

        try:
            actor_id = uuid.UUID(x_platform_actor_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="Invalid X-Platform-Actor-ID: must be a UUID"
            ) from exc

        result = await session.execute(
            select(PlatformUser).where(PlatformUser.id == actor_id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise HTTPException(status_code=401, detail="Platform actor not found")

        if not user.is_active:
            raise HTTPException(status_code=403, detail="Platform actor is inactive")

        # Bind to structlog context vars so AuditableMixin picks up actor identity.
        structlog.contextvars.bind_contextvars(
            actor_type="platform_user",
            actor_id=str(user.id),
            actor_label=user.email,
        )

        return user


CurrentPlatformUser = Annotated[PlatformUser, Depends(get_current_platform_user)]


async def get_current_superuser(
    user: CurrentPlatformUser,
) -> PlatformUser:
    """Require is_superuser=True. Build on top of get_current_platform_user."""
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser required")
    return user


CurrentSuperuser = Annotated[PlatformUser, Depends(get_current_superuser)]
```

> **Why `# type: ignore[misc]`?** mypy flags a `def` inside an `else` block as a non-trivial redefinition because it follows the `if` branch that imports a function with a different signature. The ignore is narrow and intentional — the two implementations have the same return type (`PlatformUser`); FastAPI resolves the parameters from the actual bound function, not the type hint.

- [ ] **Step 2: Verify stub mode still works (default in tests)**

```bash
python -c "
import os
os.environ['PLATFORM_AUTH_MODE'] = 'stub'
from app.platform_.auth import get_current_platform_user, CurrentPlatformUser
print('active function:', get_current_platform_user.__name__)
"
```

Expected: `active function: get_current_platform_user`

- [ ] **Step 3: Verify JWT mode binding (without actually running the function)**

```bash
python -c "
import os
# Temporarily override — lru_cache must be cleared first.
os.environ['PLATFORM_AUTH_MODE'] = 'jwt'
from app.core.config import get_settings
get_settings.cache_clear()
from app.modules.iam.dependencies import get_current_platform_user_jwt
print('jwt function available:', get_current_platform_user_jwt.__name__)
get_settings.cache_clear()  # restore
os.environ['PLATFORM_AUTH_MODE'] = 'stub'
"
```

Expected: `jwt function available: get_current_platform_user_jwt`

> **Note:** The binding in `app/platform_/auth.py` is only testable by importing the module in a process where `PLATFORM_AUTH_MODE` is set before the first import. In tests, this is ensured by `conftest.py`. Do not rely on `get_settings.cache_clear()` in production — settings are intentionally cached for the process lifetime.

- [ ] **Step 4: Run all existing tests to confirm no regressions**

```bash
pytest tests/ -v --ignore=tests/modules/iam/test_dependencies.py -x
```

Expected: all existing tests PASS (they run with `PLATFORM_AUTH_MODE=stub` via conftest.py)

- [ ] **Step 5: Commit**

```bash
git add app/platform_/auth.py
git commit -m "feat(iam): platform auth import-time binding switch (stub|jwt)"
```

---

### Task 4: `app/main.py` — TENANT_AUTH_MODE boot check

**Files:**
- Modify: `app/main.py`

Add a boot guard symmetric with the existing platform one. Also add the `verify_boot_keys` call for the JWT path.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_main.py` (create the file if it does not exist):

```python
# tests/test_main.py
"""Boot-time guard tests for app/main.py lifespan."""
import pytest


def test_tenant_auth_mode_stub_in_test_env():
    """Confirm test environment defaults to stub — existing tests are safe."""
    from app.core.config import get_settings

    assert get_settings().tenant_auth_mode == "stub"
```

- [ ] **Step 2: Run test to confirm pass (it should already pass)**

```bash
pytest tests/test_main.py -v
```

Expected: 1 test PASS

- [ ] **Step 3: Update the `lifespan` function in `app/main.py`**

The current lifespan contains:

```python
# Refuse to boot stub auth in production.
if settings.app_env == "production" and settings.platform_auth_mode == "stub":
    raise RuntimeError(
        "Refusing to boot: PLATFORM_AUTH_MODE=stub is forbidden in production. "
        "Set PLATFORM_AUTH_MODE to a non-stub value when IAM ships."
    )
```

Extend it to also guard `tenant_auth_mode`. Replace that block with:

```python
# Refuse to boot stub auth in production.
if settings.app_env == "production" and settings.platform_auth_mode == "stub":
    raise RuntimeError(
        "Refusing to boot: PLATFORM_AUTH_MODE=stub is forbidden in production. "
        "Set PLATFORM_AUTH_MODE to a non-stub value when IAM ships."
    )
if settings.app_env == "production" and settings.tenant_auth_mode == "stub":
    raise RuntimeError(
        "Refusing to boot: TENANT_AUTH_MODE=stub is forbidden in production. "
        "Set TENANT_AUTH_MODE to a non-stub value when IAM ships."
    )

# When jwt mode is active, verify signing keys exist and KEK is valid.
if settings.platform_auth_mode == "jwt" or settings.tenant_auth_mode == "jwt":
    from app.modules.iam.keys.service import verify_boot_keys
    await verify_boot_keys()
```

> If `verify_boot_keys()` is already called in the lifespan from Plan 01, update the condition to include `tenant_auth_mode == "jwt"` rather than adding a duplicate call.

- [ ] **Step 4: Run the boot check test**

```bash
pytest tests/test_main.py -v
```

Expected: 1 test PASS

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_main.py
git commit -m "feat(iam): TENANT_AUTH_MODE production boot guard + verify_boot_keys for jwt modes"
```

---

### Task 5: Tests for the real JWT dependency functions

**Files:**
- Create: `tests/modules/iam/test_dependencies.py`

These tests call the JWT dependency functions directly (not through FastAPI routing). Dependencies are passed as explicit arguments rather than resolved by FastAPI's DI engine.

- [ ] **Step 1: Write the failing tests**

```python
# tests/modules/iam/test_dependencies.py
"""Unit tests for the real JWT-validating dependency functions.

Calls get_current_platform_user_jwt and get_current_tenant_user_jwt directly
with manually-constructed inputs. FastAPI's Depends() resolution is bypassed —
we test the function logic, not the DI wiring.

The rsa_keypair fixture generates a 2048-bit key pair once per module.
Tokens are encoded with the test private key; KeyService is mocked to return
the test public key on get_verification_key().
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.security import HTTPAuthorizationCredentials

from app.modules.iam.dependencies import (
    get_current_platform_user_jwt,
    get_current_tenant_user_jwt,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def rsa_keypair() -> tuple[bytes, bytes]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def _make_platform_token(
    private_pem: bytes,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    *,
    expired: bool = False,
) -> str:
    from app.modules.iam.tokens.service import encode_access_token

    ttl = -60 if expired else 900
    return encode_access_token(
        sub=str(user_id),
        audience="platform",
        session_id=str(session_id),
        actor_type="platform_user",
        kid="test-kid",
        private_key=private_pem,
        algorithm="RS256",
        ttl=ttl,
    )


def _make_tenant_token(
    private_pem: bytes,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    slug: str = "test-sacco",
    *,
    expired: bool = False,
) -> str:
    from app.modules.iam.tokens.service import encode_access_token

    ttl = -60 if expired else 900
    return encode_access_token(
        sub=str(user_id),
        audience=f"tenant:{slug}",
        session_id=str(session_id),
        actor_type="tenant_user",
        kid="test-tenant-kid",
        private_key=private_pem,
        algorithm="RS256",
        ttl=ttl,
    )


def _make_mock_key_service(public_pem: bytes, audience: str = "platform") -> MagicMock:
    ks = MagicMock()
    ks.get_verification_key = AsyncMock(
        return_value=(public_pem, "RS256", audience)
    )
    return ks


def _make_mock_session_row(*, revoked: bool = False) -> MagicMock:
    row = MagicMock()
    row.revoked_at = datetime.now(UTC) if revoked else None
    return row


def _make_mock_platform_user(*, active: bool = True) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "admin@example.com"
    user.is_active = active
    return user


def _make_mock_tenant_user(*, active: bool = True) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "member@sacco.org"
    user.is_active = active
    return user


def _mock_request(slug: str = "test-sacco") -> MagicMock:
    req = MagicMock()
    req.app.state.redis = None
    req.headers.get = MagicMock(return_value=slug)
    return req


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="bearer", credentials=token)


# ── get_current_platform_user_jwt ─────────────────────────────────────────────


@pytest.mark.anyio
async def test_platform_jwt_dep_returns_user_for_valid_token(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    token = _make_platform_token(private_pem, user_id, session_id)

    mock_user = _make_mock_platform_user()
    mock_session_row = _make_mock_session_row()
    mock_db_session = AsyncMock()
    mock_db_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user))
    )
    mock_key_service = _make_mock_key_service(public_pem, "platform")

    with patch("app.modules.iam.dependencies.KeyService", return_value=mock_key_service), \
         patch(
             "app.modules.iam.dependencies.SessionService"
         ) as MockSvc:
        mock_svc_instance = AsyncMock()
        mock_svc_instance.get_by_session_id = AsyncMock(return_value=mock_session_row)
        MockSvc.return_value = mock_svc_instance

        result = await get_current_platform_user_jwt(
            credentials=_credentials(token),
            session=mock_db_session,
            request=_mock_request(),
        )

    assert result is mock_user


@pytest.mark.anyio
async def test_platform_jwt_dep_raises_401_for_garbage_token(rsa_keypair):
    from fastapi import HTTPException

    _, public_pem = rsa_keypair
    mock_db_session = AsyncMock()
    mock_key_service = _make_mock_key_service(public_pem, "platform")

    with patch("app.modules.iam.dependencies.KeyService", return_value=mock_key_service):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_platform_user_jwt(
                credentials=_credentials("not.a.jwt"),
                session=mock_db_session,
                request=_mock_request(),
            )
    assert exc_info.value.status_code == 401


@pytest.mark.anyio
async def test_platform_jwt_dep_raises_401_for_revoked_session(rsa_keypair):
    from fastapi import HTTPException

    private_pem, public_pem = rsa_keypair
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    token = _make_platform_token(private_pem, user_id, session_id)

    mock_key_service = _make_mock_key_service(public_pem, "platform")
    mock_db_session = AsyncMock()

    with patch("app.modules.iam.dependencies.KeyService", return_value=mock_key_service), \
         patch("app.modules.iam.dependencies.SessionService") as MockSvc:
        mock_svc_instance = AsyncMock()
        # Return a revoked session row
        mock_svc_instance.get_by_session_id = AsyncMock(
            return_value=_make_mock_session_row(revoked=True)
        )
        MockSvc.return_value = mock_svc_instance

        with pytest.raises(HTTPException) as exc_info:
            await get_current_platform_user_jwt(
                credentials=_credentials(token),
                session=mock_db_session,
                request=_mock_request(),
            )
    assert exc_info.value.status_code == 401


# ── get_current_tenant_user_jwt ───────────────────────────────────────────────


@pytest.mark.anyio
async def test_tenant_jwt_dep_returns_user_for_valid_token(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    slug = "test-sacco"
    token = _make_tenant_token(private_pem, user_id, session_id, slug)

    mock_user = _make_mock_tenant_user()
    mock_session_row = _make_mock_session_row()
    mock_tenant_db = AsyncMock()
    mock_tenant_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user))
    )
    mock_platform_db = AsyncMock()
    mock_key_service = _make_mock_key_service(public_pem, "tenant")

    with patch("app.modules.iam.dependencies.KeyService", return_value=mock_key_service), \
         patch("app.modules.iam.dependencies.SessionService") as MockSvc:
        mock_svc_instance = AsyncMock()
        mock_svc_instance.get_by_session_id = AsyncMock(return_value=mock_session_row)
        MockSvc.return_value = mock_svc_instance

        result = await get_current_tenant_user_jwt(
            credentials=_credentials(token),
            tenant_db=mock_tenant_db,
            platform_db=mock_platform_db,
            request=_mock_request(slug),
        )

    assert result is mock_user


@pytest.mark.anyio
async def test_tenant_jwt_dep_raises_401_for_wrong_audience(rsa_keypair):
    """A token issued for tenant-a must be rejected when presented to tenant-b."""
    from fastapi import HTTPException

    private_pem, public_pem = rsa_keypair
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    # Token issued for "tenant-a"
    token = _make_tenant_token(private_pem, user_id, session_id, "tenant-a")

    mock_key_service = _make_mock_key_service(public_pem, "tenant")
    mock_tenant_db = AsyncMock()
    mock_platform_db = AsyncMock()

    with patch("app.modules.iam.dependencies.KeyService", return_value=mock_key_service):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_tenant_user_jwt(
                credentials=_credentials(token),
                tenant_db=mock_tenant_db,
                platform_db=mock_platform_db,
                # Request is for "tenant-b" — audience mismatch
                request=_mock_request("tenant-b"),
            )
    assert exc_info.value.status_code == 401
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/iam/test_dependencies.py -v
```

Expected: `ImportError` or test failures because `dependencies.py` doesn't exist yet — but since Task 2 created it, these should now fail only if `encode_access_token` doesn't accept the parameters we're calling it with. Verify the token-building helpers match Plan 01's `encode_access_token` signature.

- [ ] **Step 3: Run tests to confirm pass**

```bash
pytest tests/modules/iam/test_dependencies.py -v
```

Expected: 5 tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/modules/iam/test_dependencies.py
git commit -m "test(iam): unit tests for JWT dependency functions"
```

---

## Verification Criteria

Before marking this plan complete, run the following in order:

```bash
# 1. Linting — zero errors
ruff check app/modules/iam/dependencies.py app/platform_/auth.py app/main.py

# 2. Type checking — zero errors
mypy app/modules/iam/dependencies.py app/platform_/auth.py --strict

# 3. Config tests
pytest tests/core/test_config.py -v -k "tenant_auth_mode"

# 4. Dependency unit tests
pytest tests/modules/iam/test_dependencies.py -v

# 5. Full suite — no regressions (stub mode in effect)
pytest tests/ -v
```

All commands must exit cleanly before this plan is considered complete.

---

## What is NOT in this plan

- **Wiring `CurrentTenantUser` into actual tenant routes** — future module plans (ledger, members, savings) add `user: CurrentTenantUser` to their route handlers when they're built. Plan 09 just makes it available to import.
- **Lockout checks in the JWT dependency** — the dependency intentionally skips lockout checking. Lockout (Plan 10) is enforced at the *login* endpoint, not on every authenticated request. A locked-out user simply cannot obtain new tokens.
- **Audit events on authenticated requests** — not in scope for the dependency. Audit writes happen at the service layer (Plan 11), not in the auth dependency.
- **Token refresh wired to dependency validation** — `/platform/auth/refresh` and `/auth/refresh` bypass this dependency entirely (they accept refresh tokens, not access tokens). The dependency only validates access tokens.
