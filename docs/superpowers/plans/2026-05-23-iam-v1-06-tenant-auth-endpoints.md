# IAM v1-06: Tenant Auth Endpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `POST /auth/token` (login), `POST /auth/refresh`, and `POST /auth/logout` for the tenant user audience, mirroring the platform auth endpoints (Plan 05) but operating on `TenantUser` / `TenantSession` tables and using `aud = "tenant:<slug>"` JWT claims.

**Architecture:** `TenantAuthService` is structurally identical to `PlatformAuthService` with three differences: it queries `TenantUser` instead of `PlatformUser`, creates `TenantSession` rows (no `schema=`; resolved via `search_path`), and embeds `f"tenant:{slug}"` in the JWT `aud` claim. The FastAPI dependency injects two sessions — a tenant session (for user + session DB ops) and a platform session (for `KeyService`, which reads `platform.jwt_signing_keys`). The tenant slug is extracted from the request's `X-Tenant-Slug` header (already validated by `get_tenant_session`). Lockout (Plan 10) and audit (Plan 11) are wired in later.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, PyJWT, passlib argon2id, redis-py async, pytest-anyio, httpx

---

## Required Reading (complete before starting any task)

1. `CLAUDE.md` — architectural rules, multi-tenancy via `search_path`
2. `docs/superpowers/decisions/2026-05-21-iam-architecture.md` §3, §5, §7 — token lifetimes, tenant session table, auth endpoint design
3. `docs/superpowers/specs/2026-05-21-iam-v1-design.md` §7.2 — tenant auth endpoint spec
4. `app/modules/iam/platform_auth/service.py` — Plan 05 reference implementation (mirror it)
5. `app/modules/iam/platform_auth/api.py` — Plan 05 router structure (mirror it)
6. `app/modules/iam/sessions/models.py` — `TenantSession` model (Plan 03)
7. `app/modules/iam/tenant_users/models.py` — `TenantUser` model (Plan 04)
8. `app/modules/iam/tenant_users/service.py` — `TenantUserService` (for understanding model shape; not called here)
9. `app/core/db.py` — `get_tenant_session` (reads `X-Tenant-Slug`), `get_platform_session`
10. `app/core/config.py` — `jwt_refresh_ttl_tenant_seconds`, `jwt_access_ttl_seconds`, `tenant_header`
11. `tests/conftest.py` — `tenant_session`, `platform_session`, `anyio_backend`, `test_engine` fixtures

---

## File Map

```
CREATE app/modules/iam/tenant_auth/__init__.py
CREATE app/modules/iam/tenant_auth/schemas.py  — TenantLoginRequest, TenantRefreshRequest, TenantTokenResponse
CREATE app/modules/iam/tenant_auth/service.py  — TenantAuthService: login, refresh, logout
CREATE app/modules/iam/tenant_auth/api.py      — /auth/token, /refresh, /logout router
CREATE tests/modules/iam/tenant_auth/__init__.py
CREATE tests/modules/iam/tenant_auth/test_tenant_auth_service.py
CREATE tests/modules/iam/tenant_auth/test_tenant_auth_api.py
MODIFY app/main.py                             — include tenant_auth router
```

---

### Task 1: Pydantic schemas

**Files:**
- Create: `app/modules/iam/tenant_auth/__init__.py`
- Create: `app/modules/iam/tenant_auth/schemas.py`
- Create: `tests/modules/iam/tenant_auth/__init__.py`

Schemas require no dedicated failing test — validated implicitly by service and API tests.

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p app/modules/iam/tenant_auth tests/modules/iam/tenant_auth
touch app/modules/iam/tenant_auth/__init__.py tests/modules/iam/tenant_auth/__init__.py
```

- [ ] **Step 2: Create `app/modules/iam/tenant_auth/schemas.py`**

```python
"""Pydantic schemas for tenant auth endpoints.

TenantLoginRequest    — POST /auth/token body
TenantRefreshRequest  — POST /auth/refresh body
TenantTokenResponse   — response body for token and refresh endpoints

These are structurally identical to their platform_auth counterparts but
kept separate to avoid cross-module dependencies between platform_auth and
tenant_auth.
"""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class TenantLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TenantRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TenantTokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires
```

- [ ] **Step 3: Verify schemas parse cleanly**

```bash
python -c "
from app.modules.iam.tenant_auth.schemas import (
    TenantLoginRequest, TenantRefreshRequest, TenantTokenResponse
)
r = TenantLoginRequest(email='user@sacco.org', password='secret')
assert r.email == 'user@sacco.org'
rr = TenantRefreshRequest(refresh_token='tok')
resp = TenantTokenResponse(access_token='a', expires_in=900)
assert resp.token_type == 'bearer'
assert resp.refresh_token is None
print('schemas OK')
"
```

Expected: `schemas OK`

- [ ] **Step 4: Commit**

```bash
git add app/modules/iam/tenant_auth/ tests/modules/iam/tenant_auth/
git commit -m "feat(iam): tenant_auth Pydantic schemas (login, refresh, token response)"
```

---

### Task 2: TenantAuthService — login, refresh, logout

**Files:**
- Create: `app/modules/iam/tenant_auth/service.py`
- Create: `tests/modules/iam/tenant_auth/test_tenant_auth_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/modules/iam/tenant_auth/test_tenant_auth_service.py
"""Integration tests for TenantAuthService.

Uses a real PostgreSQL test DB (tenant_session fixture for TenantUser /
TenantSession, platform_session for KeyService), a module-scoped test RSA
keypair, and an AsyncMock for Redis. argon2id is exercised for real via the
pre-computed _HASHED_PASSWORD constant (paid once at import, ~300 ms).

Test speed: ~8–12 s due to argon2id verify calls.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.modules.iam.passwords.service import hash_password
from app.modules.iam.tenant_auth.service import TenantAuthService
from app.modules.iam.tenant_users.models import TenantUser

# ── Pre-computed test data ────────────────────────────────────────────────────

_PASSWORD = "CorrectHorseBatteryStaple!"
# One argon2id hash computed at module import (~300 ms). Shared across tests.
_HASHED_PASSWORD = hash_password(_PASSWORD)
_TEST_SLUG = "test-sacco"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def rsa_keypair() -> tuple[bytes, bytes]:
    """Generate a 2048-bit RSA keypair once per test module."""
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


@pytest.fixture
def mock_key_service(rsa_keypair: tuple[bytes, bytes]) -> MagicMock:
    """KeyService stub returning the test RSA keypair for the 'tenant' audience."""
    private_pem, public_pem = rsa_keypair
    ks = MagicMock()
    # Note: key service is called with "tenant" (the DB audience column value),
    # NOT the full "tenant:<slug>" JWT audience claim.
    ks.get_active_signing_key = AsyncMock(
        return_value=("test-tenant-kid", private_pem, "RS256")
    )
    ks.get_verification_key = AsyncMock(
        return_value=(public_pem, "RS256", "tenant")
    )
    return ks


@pytest.fixture
async def active_tenant_user(tenant_session) -> TenantUser:
    """Insert a real TenantUser with a known hashed password."""
    user = TenantUser(
        id=uuid.uuid4(),
        email="tenant-auth-test@example.com",
        full_name="Tenant Auth Test",
        hashed_password=_HASHED_PASSWORD,
        is_active=True,
        is_admin=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    tenant_session.add(user)
    await tenant_session.flush()
    return user


@pytest.fixture
async def inactive_tenant_user(tenant_session) -> TenantUser:
    """Insert a deactivated TenantUser."""
    user = TenantUser(
        id=uuid.uuid4(),
        email="tenant-inactive@example.com",
        full_name="Inactive Tenant User",
        hashed_password=_HASHED_PASSWORD,
        is_active=False,
        is_admin=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    tenant_session.add(user)
    await tenant_session.flush()
    return user


def _make_service(tenant_db, key_service, redis=None) -> TenantAuthService:
    return TenantAuthService(
        db=tenant_db,
        key_service=key_service,
        redis=redis,
        tenant_slug=_TEST_SLUG,
    )


# ── login ─────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_tenant_login_returns_token_response(
    tenant_session, mock_key_service, active_tenant_user
):
    svc = _make_service(tenant_session, mock_key_service)
    response = await svc.login(
        email=active_tenant_user.email,
        password=_PASSWORD,
        user_agent="pytest/1.0",
        ip_address="127.0.0.1",
    )
    assert response.access_token
    assert response.refresh_token
    assert response.token_type == "bearer"
    assert response.expires_in > 0


@pytest.mark.anyio
async def test_tenant_login_access_token_has_tenant_audience(
    tenant_session, mock_key_service, rsa_keypair, active_tenant_user
):
    import jwt as pyjwt

    _, public_pem = rsa_keypair
    svc = _make_service(tenant_session, mock_key_service)
    response = await svc.login(
        email=active_tenant_user.email, password=_PASSWORD,
        user_agent=None, ip_address=None,
    )
    # Audience must be "tenant:<slug>", not just "tenant"
    expected_audience = f"tenant:{_TEST_SLUG}"
    claims = pyjwt.decode(
        response.access_token,
        public_pem,
        algorithms=["RS256"],
        audience=expected_audience,
    )
    assert claims["sub"] == str(active_tenant_user.id)
    assert claims["aud"] == expected_audience
    assert claims["actor_type"] == "tenant_user"
    assert "session_id" in claims


@pytest.mark.anyio
async def test_tenant_login_wrong_password_raises_401(
    tenant_session, mock_key_service, active_tenant_user
):
    from fastapi import HTTPException

    svc = _make_service(tenant_session, mock_key_service)
    with pytest.raises(HTTPException) as exc_info:
        await svc.login(
            email=active_tenant_user.email,
            password="WrongPassword!!!!",
            user_agent=None,
            ip_address=None,
        )
    assert exc_info.value.status_code == 401


@pytest.mark.anyio
async def test_tenant_login_unknown_email_raises_401(tenant_session, mock_key_service):
    from fastapi import HTTPException

    svc = _make_service(tenant_session, mock_key_service)
    with pytest.raises(HTTPException) as exc_info:
        await svc.login(
            email="nobody@nowhere.com",
            password=_PASSWORD,
            user_agent=None,
            ip_address=None,
        )
    assert exc_info.value.status_code == 401


@pytest.mark.anyio
async def test_tenant_login_inactive_user_raises_401(
    tenant_session, mock_key_service, inactive_tenant_user
):
    from fastapi import HTTPException

    svc = _make_service(tenant_session, mock_key_service)
    with pytest.raises(HTTPException) as exc_info:
        await svc.login(
            email=inactive_tenant_user.email,
            password=_PASSWORD,
            user_agent=None,
            ip_address=None,
        )
    assert exc_info.value.status_code == 401


# ── refresh ───────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_tenant_refresh_returns_new_access_token(
    tenant_session, mock_key_service, active_tenant_user
):
    svc = _make_service(tenant_session, mock_key_service)
    login_resp = await svc.login(
        email=active_tenant_user.email, password=_PASSWORD,
        user_agent=None, ip_address=None,
    )
    refresh_resp = await svc.refresh(login_resp.refresh_token)

    assert refresh_resp.access_token
    assert refresh_resp.access_token != login_resp.access_token
    assert refresh_resp.refresh_token is None  # no new refresh token issued
    assert refresh_resp.token_type == "bearer"


@pytest.mark.anyio
async def test_tenant_refresh_with_garbage_token_raises_401(
    tenant_session, mock_key_service
):
    from fastapi import HTTPException

    svc = _make_service(tenant_session, mock_key_service)
    with pytest.raises(HTTPException) as exc_info:
        await svc.refresh("not.a.valid.jwt")
    assert exc_info.value.status_code == 401


@pytest.mark.anyio
async def test_tenant_refresh_after_logout_raises_401(
    tenant_session, mock_key_service, active_tenant_user
):
    from fastapi import HTTPException

    svc = _make_service(tenant_session, mock_key_service)
    login_resp = await svc.login(
        email=active_tenant_user.email, password=_PASSWORD,
        user_agent=None, ip_address=None,
    )
    await svc.logout(login_resp.access_token)

    with pytest.raises(HTTPException) as exc_info:
        await svc.refresh(login_resp.refresh_token)
    assert exc_info.value.status_code == 401


# ── logout ────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_tenant_logout_revokes_session(
    tenant_session, mock_key_service, active_tenant_user
):
    svc = _make_service(tenant_session, mock_key_service)
    login_resp = await svc.login(
        email=active_tenant_user.email, password=_PASSWORD,
        user_agent=None, ip_address=None,
    )
    await svc.logout(login_resp.access_token)  # must not raise


@pytest.mark.anyio
async def test_tenant_logout_with_invalid_token_raises_401(
    tenant_session, mock_key_service
):
    from fastapi import HTTPException

    svc = _make_service(tenant_session, mock_key_service)
    with pytest.raises(HTTPException) as exc_info:
        await svc.logout("not.a.valid.jwt")
    assert exc_info.value.status_code == 401
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/iam/tenant_auth/test_tenant_auth_service.py -v
```

Expected: `ImportError` — `tenant_auth/service.py` does not exist yet

- [ ] **Step 3: Create `app/modules/iam/tenant_auth/service.py`**

```python
"""TenantAuthService — login, refresh, and logout for tenant users.

Mirrors PlatformAuthService (Plan 05) with three differences:
  1. Queries TenantUser instead of PlatformUser.
  2. Creates TenantSession rows (no schema= — resolved via search_path).
  3. JWT audience claim is "tenant:<slug>" rather than "platform".
     KeyService is still called with audience="tenant" (the DB column value).

Plans that modify this file later:
  Plan 10: lockout.record_attempt() / lockout.is_locked() calls in login()
  Plan 11: structlog audit event calls in login(), refresh(), logout()
  Plan 07: add me() method
  Plan 08: add reset_request() and reset_confirm() methods
"""
from __future__ import annotations

import uuid

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.iam.passwords.service import hash_password, needs_rehash, verify_password
from app.modules.iam.sessions.models import TenantSession
from app.modules.iam.sessions.service import SessionService
from app.modules.iam.tenant_auth.schemas import TenantTokenResponse
from app.modules.iam.tenant_users.models import TenantUser
from app.modules.iam.tokens.service import (
    decode_token,
    encode_access_token,
    encode_refresh_token,
)

_log = structlog.get_logger(__name__)

# Signing key DB column value — used to look up the key, not the JWT aud claim.
_KEY_AUDIENCE = "tenant"


class TenantAuthService:
    """Orchestrates tenant user authentication.

    Args:
        db:          AsyncSession scoped to the tenant schema (search_path set).
        key_service: KeyService instance backed by a platform schema session.
        redis:       Optional Redis async client for O(1) jti revocation checks.
        tenant_slug: Slug of the current tenant (from X-Tenant-Slug header).
                     Embedded in the JWT ``aud`` claim as ``"tenant:<slug>"``.
    """

    def __init__(
        self,
        db: AsyncSession,
        key_service: object,  # KeyService — typed as object to avoid circular import
        redis: object | None,
        tenant_slug: str,
    ) -> None:
        self._db = db
        self._key_service = key_service
        self._redis = redis
        self._slug = tenant_slug
        self._audience = f"tenant:{tenant_slug}"
        self._session_svc = SessionService(
            db=db,
            model_cls=TenantSession,
            redis=redis,
        )

    # ── login ─────────────────────────────────────────────────────────────

    async def login(
        self,
        email: str,
        password: str,
        user_agent: str | None,
        ip_address: str | None,
    ) -> TenantTokenResponse:
        """Full login flow: verify credentials → create session → issue tokens.

        Raises:
            HTTPException 401: unknown email, wrong password, or inactive user.
        """
        settings = get_settings()

        # 1. Look up user — generic 401 for both unknown and inactive to
        #    prevent user enumeration. Plan 10 adds lockout.record_attempt()
        #    and lockout.is_locked() calls here.
        result = await self._db.execute(
            select(TenantUser).where(TenantUser.email == email)
        )
        user = result.scalar_one_or_none()

        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # 2. Verify password.
        if not user.hashed_password or not verify_password(password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # 3. Transparent rehash — upgrade argon2id parameters if needed.
        if needs_rehash(user.hashed_password):
            user.hashed_password = hash_password(password)

        # 4. Fetch active signing key for the tenant audience (DB column = "tenant").
        kid, private_key, algorithm = await self._key_service.get_active_signing_key(
            _KEY_AUDIENCE
        )

        # 5. Pre-generate JTI — same value stored on session row and in the
        #    refresh token claims.
        jti = str(uuid.uuid4())

        # 6. Create session row.
        session_row = await self._session_svc.create(
            user_id=user.id,
            jti=jti,
            user_agent=user_agent,
            ip_address=ip_address,
            refresh_ttl_seconds=settings.jwt_refresh_ttl_tenant_seconds,
        )

        # 7. Issue tokens. JWT aud = "tenant:<slug>".
        access_ttl = settings.jwt_access_ttl_seconds
        access_token = encode_access_token(
            sub=str(user.id),
            audience=self._audience,
            session_id=str(session_row.id),
            actor_type="tenant_user",
            kid=kid,
            private_key=private_key,
            algorithm=algorithm,
            ttl=access_ttl,
        )
        refresh_token = encode_refresh_token(
            sub=str(user.id),
            audience=self._audience,
            session_id=str(session_row.id),
            jti=jti,
            kid=kid,
            private_key=private_key,
            algorithm=algorithm,
            ttl=settings.jwt_refresh_ttl_tenant_seconds,
        )

        # Plan 11 adds: audit("tenant_auth.login_success", user_id=user.id)
        # Plan 10 adds: lockout.reset(email) after successful login

        _log.info("tenant_auth.login_success", user_id=str(user.id), tenant=self._slug)
        return TenantTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=access_ttl,
        )

    # ── refresh ───────────────────────────────────────────────────────────

    async def refresh(self, refresh_token: str) -> TenantTokenResponse:
        """Issue a new access token from a valid, non-revoked refresh token.

        Raises:
            HTTPException 401: malformed token, invalid signature, expired token,
                               or revoked/expired session.
        """
        settings = get_settings()

        # 1. Decode and validate the refresh token (signature + expiry + audience).
        #    audience must match "tenant:<slug>" exactly — a token issued for
        #    tenant-a cannot be used against tenant-b.
        try:
            claims = await decode_token(
                token=refresh_token,
                audience=self._audience,
                key_service=self._key_service,
            )
        except Exception:
            raise HTTPException(
                status_code=401, detail="Invalid or expired refresh token"
            )

        session_id_str = claims.get("session_id")
        jti = claims.get("jti")
        if not session_id_str or not jti:
            raise HTTPException(status_code=401, detail="Malformed token claims")

        try:
            session_id = uuid.UUID(session_id_str)
        except ValueError:
            raise HTTPException(status_code=401, detail="Malformed session_id claim")

        # 2. Fetch session — must exist, not be revoked, not be expired.
        session_row = await self._session_svc.get_by_session_id(session_id)
        if session_row is None:
            raise HTTPException(status_code=401, detail="Session not found")
        if session_row.revoked_at is not None:
            raise HTTPException(status_code=401, detail="Session has been revoked")

        from datetime import UTC, datetime
        if session_row.expires_at < datetime.now(UTC):
            raise HTTPException(status_code=401, detail="Session has expired")

        # 3. Verify jti matches the stored refresh jti (defense in depth).
        if session_row.jti != jti:
            raise HTTPException(status_code=401, detail="Token jti mismatch")

        # 4. Check jti is still valid in Redis (fast revocation path).
        if not await self._session_svc.is_jti_valid(jti):
            raise HTTPException(status_code=401, detail="Session has been revoked")

        # 5. Fetch signing key and issue a new access token.
        kid, private_key, algorithm = await self._key_service.get_active_signing_key(
            _KEY_AUDIENCE
        )
        access_ttl = settings.jwt_access_ttl_seconds
        access_token = encode_access_token(
            sub=claims["sub"],
            audience=self._audience,
            session_id=session_id_str,
            actor_type="tenant_user",
            kid=kid,
            private_key=private_key,
            algorithm=algorithm,
            ttl=access_ttl,
        )

        # 6. Update last_used_at on the session row.
        await self._session_svc.update_last_used(session_id)

        # Plan 11 adds: audit("tenant_auth.refresh", ...)

        _log.info("tenant_auth.refresh", session_id=session_id_str, tenant=self._slug)
        return TenantTokenResponse(
            access_token=access_token,
            refresh_token=None,
            expires_in=access_ttl,
        )

    # ── logout ────────────────────────────────────────────────────────────

    async def logout(self, access_token: str) -> None:
        """Revoke the session associated with the given access token.

        Raises:
            HTTPException 401: malformed or invalid access token.
        """
        try:
            claims = await decode_token(
                token=access_token,
                audience=self._audience,
                key_service=self._key_service,
            )
        except Exception:
            raise HTTPException(
                status_code=401, detail="Invalid or expired access token"
            )

        session_id_str = claims.get("session_id")
        if not session_id_str:
            raise HTTPException(status_code=401, detail="Malformed token claims")

        try:
            session_id = uuid.UUID(session_id_str)
        except ValueError:
            raise HTTPException(status_code=401, detail="Malformed session_id claim")

        await self._session_svc.revoke(session_id)

        # Plan 11 adds: audit("tenant_auth.logout", ...)

        _log.info("tenant_auth.logout", session_id=session_id_str, tenant=self._slug)
```

- [ ] **Step 4: Run service tests to confirm pass**

```bash
pytest tests/modules/iam/tenant_auth/test_tenant_auth_service.py -v
```

Expected: all 11 tests PASS. Total time ~8–12 s (argon2id).

- [ ] **Step 5: Commit**

```bash
git add app/modules/iam/tenant_auth/service.py \
        tests/modules/iam/tenant_auth/test_tenant_auth_service.py
git commit -m "feat(iam): TenantAuthService — login, refresh, logout"
```

---

### Task 3: Tenant auth API router

**Files:**
- Create: `app/modules/iam/tenant_auth/api.py`
- Create: `tests/modules/iam/tenant_auth/test_tenant_auth_api.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write the failing API tests**

```python
# tests/modules/iam/tenant_auth/test_tenant_auth_api.py
"""HTTP-level tests for /auth/* tenant endpoints.

Uses FastAPI dependency_overrides to inject a fake TenantAuthService.
The tests verify routing, status codes, and response shapes only —
internal auth logic is covered by test_tenant_auth_service.py.

The X-Tenant-Slug header must be present on all requests because
get_tenant_session (FastAPI dependency) raises 400 without it.
However, since we override get_tenant_auth_service entirely, the
real get_tenant_session is never called — the header is still
included in requests for realism but is not validated.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock

from app.main import app
from app.modules.iam.tenant_auth.schemas import TenantTokenResponse

_SLUG_HEADER = {"X-Tenant-Slug": "test-sacco"}


def _ok_token_response(*, with_refresh: bool = True) -> TenantTokenResponse:
    return TenantTokenResponse(
        access_token="access.token.here",
        refresh_token="refresh.token.here" if with_refresh else None,
        expires_in=900,
    )


# ── /auth/token ───────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_tenant_login_returns_200_with_tokens():
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    mock_svc = AsyncMock()
    mock_svc.login = AsyncMock(return_value=_ok_token_response())

    app.dependency_overrides[get_tenant_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/token",
                json={"email": "user@sacco.org", "password": "supersecret123"},
                headers=_SLUG_HEADER,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["access_token"] == "access.token.here"
        assert body["refresh_token"] == "refresh.token.here"
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 900
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)


@pytest.mark.anyio
async def test_tenant_login_returns_401_on_invalid_credentials():
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    mock_svc = AsyncMock()
    mock_svc.login = AsyncMock(
        side_effect=HTTPException(status_code=401, detail="Invalid credentials")
    )

    app.dependency_overrides[get_tenant_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/token",
                json={"email": "nobody@sacco.org", "password": "wrong"},
                headers=_SLUG_HEADER,
            )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)


@pytest.mark.anyio
async def test_tenant_login_returns_422_for_missing_fields():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/auth/token", json={}, headers=_SLUG_HEADER)
    assert resp.status_code == 422


# ── /auth/refresh ─────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_tenant_refresh_returns_200_with_new_access_token():
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    mock_svc = AsyncMock()
    mock_svc.refresh = AsyncMock(return_value=_ok_token_response(with_refresh=False))

    app.dependency_overrides[get_tenant_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/refresh",
                json={"refresh_token": "some.refresh.token"},
                headers=_SLUG_HEADER,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["access_token"] == "access.token.here"
        assert body["refresh_token"] is None
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)


@pytest.mark.anyio
async def test_tenant_refresh_returns_401_for_invalid_token():
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    mock_svc = AsyncMock()
    mock_svc.refresh = AsyncMock(
        side_effect=HTTPException(
            status_code=401, detail="Invalid or expired refresh token"
        )
    )

    app.dependency_overrides[get_tenant_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/refresh",
                json={"refresh_token": "garbage"},
                headers=_SLUG_HEADER,
            )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)


# ── /auth/logout ──────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_tenant_logout_returns_204():
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    mock_svc = AsyncMock()
    mock_svc.logout = AsyncMock(return_value=None)

    app.dependency_overrides[get_tenant_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/logout",
                headers={**_SLUG_HEADER, "Authorization": "Bearer some.valid.token"},
            )
        assert resp.status_code == 204
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)


@pytest.mark.anyio
async def test_tenant_logout_returns_401_or_403_without_bearer():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/auth/logout", headers=_SLUG_HEADER)
    # FastAPI HTTPBearer returns 403 when the header is absent
    assert resp.status_code in (401, 403)


@pytest.mark.anyio
async def test_tenant_logout_returns_401_for_invalid_token():
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    mock_svc = AsyncMock()
    mock_svc.logout = AsyncMock(
        side_effect=HTTPException(
            status_code=401, detail="Invalid or expired access token"
        )
    )

    app.dependency_overrides[get_tenant_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/logout",
                headers={**_SLUG_HEADER, "Authorization": "Bearer invalid.token"},
            )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/iam/tenant_auth/test_tenant_auth_api.py -v
```

Expected: `ImportError` — `tenant_auth/api.py` does not exist yet

- [ ] **Step 3: Create `app/modules/iam/tenant_auth/api.py`**

```python
"""FastAPI router for /auth/* tenant endpoints.

Three endpoints in this file:
  POST /auth/token   — login (no auth required; X-Tenant-Slug required)
  POST /auth/refresh — exchange refresh token for new access token (no auth)
  POST /auth/logout  — revoke session (Bearer access token required)

GET /auth/me is added in Plan 07.
Password reset endpoints are added in Plan 08.

Design note: the FastAPI dependency `get_tenant_auth_service` must inject
BOTH a tenant session (for TenantUser / TenantSession DB operations) AND a
platform session (for KeyService, which reads platform.jwt_signing_keys).
The tenant slug is extracted from the X-Tenant-Slug request header.
"""
from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.db import get_platform_session, get_tenant_session
from app.modules.iam.keys.service import KeyService
from app.modules.iam.tenant_auth.schemas import (
    TenantLoginRequest,
    TenantRefreshRequest,
    TenantTokenResponse,
)
from app.modules.iam.tenant_auth.service import TenantAuthService

router = APIRouter(prefix="/auth", tags=["tenant-auth"])
_log = structlog.get_logger(__name__)
_bearer = HTTPBearer()


async def get_tenant_auth_service(
    request: Request,
    tenant_db: Annotated[object, Depends(get_tenant_session)],
    platform_db: Annotated[object, Depends(get_platform_session)],
) -> TenantAuthService:
    """FastAPI dependency that constructs a TenantAuthService per request.

    Two sessions are injected:
    - tenant_db: scoped to the tenant schema (search_path set by get_tenant_session).
      Used for TenantUser lookups and TenantSession creation.
    - platform_db: scoped to the platform schema.
      Used by KeyService to read platform.jwt_signing_keys.

    The tenant slug is read from the configured tenant_header (X-Tenant-Slug by
    default). get_tenant_session has already validated it — re-reading here is
    safe since the header value is immutable within a single request.
    """
    settings = get_settings()
    tenant_slug = request.headers.get(settings.tenant_header, "")
    redis = getattr(request.app.state, "redis", None)
    key_service = KeyService(db=platform_db)
    return TenantAuthService(
        db=tenant_db,
        key_service=key_service,
        redis=redis,
        tenant_slug=tenant_slug,
    )


TenantAuth = Annotated[TenantAuthService, Depends(get_tenant_auth_service)]


@router.post("/token", response_model=TenantTokenResponse)
async def tenant_login(
    body: TenantLoginRequest,
    request: Request,
    svc: TenantAuth,
) -> TenantTokenResponse:
    """Exchange email + password for an access token and refresh token."""
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    return await svc.login(
        email=body.email,
        password=body.password,
        user_agent=user_agent,
        ip_address=ip_address,
    )


@router.post("/refresh", response_model=TenantTokenResponse)
async def tenant_refresh(
    body: TenantRefreshRequest,
    svc: TenantAuth,
) -> TenantTokenResponse:
    """Exchange a valid refresh token for a new access token."""
    return await svc.refresh(body.refresh_token)


@router.post("/logout", status_code=204)
async def tenant_logout(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    svc: TenantAuth,
) -> Response:
    """Revoke the session associated with the provided Bearer access token."""
    await svc.logout(credentials.credentials)
    return Response(status_code=204)
```

- [ ] **Step 4: Wire the router into `app/main.py`**

Add the import alongside the existing IAM router import:

```python
from app.modules.iam.tenant_auth.api import router as tenant_auth_router
```

Then add the `include_router` call. The relevant section after the edit:

```python
from app.modules.maker_checker.api import router as maker_checker_router
from app.modules.iam.platform_auth.api import router as platform_auth_router
from app.modules.iam.tenant_auth.api import router as tenant_auth_router
from app.platform_.tenants.api import router as platform_tenants_router
from app.platform_.users.api import router as platform_users_router

# ...

app.include_router(maker_checker_router)
app.include_router(platform_auth_router)
app.include_router(tenant_auth_router)
app.include_router(platform_tenants_router)
app.include_router(platform_users_router)
```

- [ ] **Step 5: Run API tests to confirm pass**

```bash
pytest tests/modules/iam/tenant_auth/test_tenant_auth_api.py -v
```

Expected: all 8 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/modules/iam/tenant_auth/api.py \
        tests/modules/iam/tenant_auth/test_tenant_auth_api.py \
        app/main.py
git commit -m "feat(iam): /auth/token, /refresh, /logout tenant endpoints"
```

---

## Verification Criteria

Before marking this plan complete, run the following in order:

```bash
# 1. Linting — zero errors
ruff check app/modules/iam/tenant_auth/

# 2. Type checking — zero errors
mypy app/modules/iam/tenant_auth/ --strict

# 3. Service tests (argon2id — ~8–12 s)
pytest tests/modules/iam/tenant_auth/test_tenant_auth_service.py -v

# 4. API tests (fast — mocked service)
pytest tests/modules/iam/tenant_auth/test_tenant_auth_api.py -v

# 5. Platform auth regression (must still pass after main.py change)
pytest tests/modules/iam/platform_auth/ -v

# 6. Full suite — no regressions
pytest tests/ -v
```

All commands must exit cleanly before this plan is considered complete.

---

## What is NOT in this plan

- **`GET /auth/me`** — added in Plan 07 alongside `GET /platform/auth/me`.
- **Password reset endpoints** (`/auth/password-reset/request`, `/auth/password-reset/confirm`) — added in Plan 08.
- **Account lockout** (failed-attempt tracking, 423 responses) — added in Plan 10. Plan 10 modifies `login()` in `service.py` to call `lockout.record_attempt()` and `lockout.is_locked()`.
- **Audit events** (`tenant_auth.login_success`, `tenant_auth.refresh`, `tenant_auth.logout`) — added in Plan 11.
- **Real JWT-validating `get_current_tenant_user`** — introduced as a new dependency in Plan 09. Plan 09 creates `app/modules/iam/dependencies.py` and binds it into tenant routes.
- **`TenantUserService` CRUD endpoints** — those are a future IAM v2 concern. Plan 04 provides the service; no router is wired in IAM v1.
