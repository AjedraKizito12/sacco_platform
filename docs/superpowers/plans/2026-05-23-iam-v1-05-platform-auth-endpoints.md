# IAM v1-05: Platform Auth Endpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `POST /platform/auth/token` (login), `POST /platform/auth/refresh`, and `POST /platform/auth/logout` for the platform user audience, wiring together `KeyService`, `TokenService`, `SessionService`, and `hash_password`/`verify_password` into a single `PlatformAuthService`.

**Architecture:** `PlatformAuthService` owns the login, refresh, and logout state machines. It receives a DB session, a `KeyService` instance, and an optional Redis client; it constructs a `SessionService` internally for session management. The FastAPI router exposes three endpoints on `router = APIRouter(prefix="/platform/auth", tags=["platform-auth"])`. Lockout wiring is deferred to Plan 10; audit events are deferred to Plan 11 — both plans modify this service's methods in place. The `/platform/auth/me` endpoint is Plan 07.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, PyJWT (via `app.modules.iam.tokens.service`), passlib argon2id (via `app.modules.iam.passwords.service`), redis-py async, pytest-anyio, httpx

---

## Required Reading (complete before starting any task)

1. `CLAUDE.md` — architectural rules; confirm no password logic in `platform_`
2. `docs/superpowers/decisions/2026-05-21-iam-architecture.md` §3, §5, §7 — token lifetimes, session tables, auth endpoint design
3. `docs/superpowers/specs/2026-05-21-iam-v1-design.md` §7.1 — login/refresh/logout flow spec
4. `app/modules/iam/tokens/service.py` — `encode_access_token`, `encode_refresh_token`, `decode_token`, `get_unverified_kid` (Plan 01)
5. `app/modules/iam/keys/service.py` — `KeyService.get_active_signing_key`, `KeyService.get_verification_key` (Plan 01)
6. `app/modules/iam/sessions/service.py` — `SessionService` constructor and `create`, `get_by_session_id`, `revoke`, `is_jti_valid`, `update_last_used` (Plan 03)
7. `app/modules/iam/sessions/models.py` — `PlatformSession` (Plan 03)
8. `app/modules/iam/passwords/service.py` — `verify_password`, `needs_rehash`, `hash_password` (Plan 02)
9. `app/platform_/models.py` — `PlatformUser` (email, hashed_password, is_active, is_superuser)
10. `app/core/config.py` — `get_settings()`, `jwt_access_ttl_seconds`, `jwt_refresh_ttl_platform_seconds`
11. `app/main.py` — lifespan, `app.state.redis`, existing router includes
12. `tests/conftest.py` — `platform_session`, `anyio_backend`, `test_engine` fixtures

---

## Prerequisite Check: `encode_refresh_token` must accept `jti`

Before starting Task 2, open `app/modules/iam/tokens/service.py` and verify the signature of `encode_refresh_token`. It **must** accept a `jti: str` parameter so that the caller can pre-generate the JTI, store it on the session row, and embed the same value in the refresh token.

If the existing signature is:
```python
def encode_refresh_token(sub: str, audience: str, session_id: str, kid: str, private_key: bytes, algorithm: str, ttl: int) -> str:
```

Update it to:
```python
def encode_refresh_token(sub: str, audience: str, session_id: str, jti: str, kid: str, private_key: bytes, algorithm: str, ttl: int) -> str:
```

Inside the function body, replace any internal `jti = str(uuid.uuid4())` with the passed-in `jti`. Confirm all existing token tests still pass:

```bash
pytest tests/modules/iam/tokens/ -v
```

Expected: all existing tests PASS. If a test hardcodes a call without `jti`, update that call to pass `jti=str(uuid.uuid4())`.

---

## File Map

```
MODIFY app/modules/iam/tokens/service.py         — add jti parameter to encode_refresh_token (see prerequisite)
CREATE app/modules/iam/platform_auth/__init__.py
CREATE app/modules/iam/platform_auth/schemas.py  — PlatformLoginRequest, PlatformRefreshRequest, PlatformTokenResponse
CREATE app/modules/iam/platform_auth/service.py  — PlatformAuthService: login, refresh, logout
CREATE app/modules/iam/platform_auth/api.py      — /platform/auth/token, /refresh, /logout router
CREATE tests/modules/iam/platform_auth/__init__.py
CREATE tests/modules/iam/platform_auth/test_platform_auth_service.py
CREATE tests/modules/iam/platform_auth/test_platform_auth_api.py
MODIFY app/main.py                               — include platform_auth router
MODIFY tests/conftest.py                         — register PlatformSession in test_engine (if not already done by Plan 03)
```

---

### Task 1: Pydantic schemas

**Files:**
- Create: `app/modules/iam/platform_auth/__init__.py`
- Create: `app/modules/iam/platform_auth/schemas.py`
- Create: `tests/modules/iam/platform_auth/__init__.py`

Schemas require no dedicated failing test — they are validated implicitly by the service and API tests in Tasks 2–3.

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p app/modules/iam/platform_auth tests/modules/iam/platform_auth
touch app/modules/iam/platform_auth/__init__.py tests/modules/iam/platform_auth/__init__.py
```

- [ ] **Step 2: Create `app/modules/iam/platform_auth/schemas.py`**

```python
"""Pydantic schemas for platform auth endpoints.

PlatformLoginRequest   — POST /platform/auth/token body
PlatformRefreshRequest — POST /platform/auth/refresh body
PlatformTokenResponse  — response body for token and refresh endpoints
"""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class PlatformLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class PlatformRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class PlatformTokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires
```

- [ ] **Step 3: Verify schemas parse cleanly**

```bash
python -c "
from app.modules.iam.platform_auth.schemas import (
    PlatformLoginRequest, PlatformRefreshRequest, PlatformTokenResponse
)
r = PlatformLoginRequest(email='a@b.com', password='secret')
assert r.email == 'a@b.com'
rr = PlatformRefreshRequest(refresh_token='tok')
resp = PlatformTokenResponse(access_token='a', refresh_token='r', expires_in=900)
assert resp.token_type == 'bearer'
print('schemas OK')
"
```

Expected: `schemas OK`

- [ ] **Step 4: Commit**

```bash
git add app/modules/iam/platform_auth/ tests/modules/iam/platform_auth/
git commit -m "feat(iam): platform_auth Pydantic schemas (login, refresh, token response)"
```

---

### Task 2: PlatformAuthService — login, refresh, logout

**Files:**
- Create: `app/modules/iam/platform_auth/service.py`
- Create: `tests/modules/iam/platform_auth/test_platform_auth_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/modules/iam/platform_auth/test_platform_auth_service.py
"""Integration tests for PlatformAuthService.

These tests use a real PostgreSQL test DB (platform_session fixture) and a
real RSA keypair generated once per test session. Redis is mocked with
AsyncMock. hash_password / verify_password run the real argon2id — the
pre-computed _HASHED_PASSWORD module constant pays this cost only once.

Test speed: argon2id hash ~200–400 ms. Each verify call is similar. With
~10 tests and one pre-hash at import, expect ~6–8 s total for this file.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.modules.iam.passwords.service import hash_password
from app.modules.iam.platform_auth.service import PlatformAuthService
from app.platform_.models import PlatformUser

# ── Pre-computed test data ────────────────────────────────────────────────────

_PASSWORD = "CorrectHorseBatteryStaple!"
# Computed once at module import time (~300 ms). All tests share this hash.
_HASHED_PASSWORD = hash_password(_PASSWORD)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def rsa_keypair() -> tuple[bytes, bytes]:
    """Generate a 2048-bit RSA keypair. scope=module — generated once."""
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
    """KeyService stub returning the test RSA keypair."""
    private_pem, public_pem = rsa_keypair
    ks = MagicMock()
    ks.get_active_signing_key = AsyncMock(
        return_value=("test-kid", private_pem, "RS256")
    )
    ks.get_verification_key = AsyncMock(
        return_value=(public_pem, "RS256", "platform")
    )
    return ks


@pytest.fixture
async def active_user(platform_session) -> PlatformUser:
    """Insert a real PlatformUser with a known hashed password."""
    user = PlatformUser(
        id=uuid.uuid4(),
        email="platform-auth-test@example.com",
        full_name="Platform Auth Test",
        hashed_password=_HASHED_PASSWORD,
        is_active=True,
        is_superuser=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    platform_session.add(user)
    await platform_session.flush()
    return user


@pytest.fixture
async def inactive_user(platform_session) -> PlatformUser:
    """Insert a PlatformUser that is deactivated."""
    user = PlatformUser(
        id=uuid.uuid4(),
        email="platform-inactive@example.com",
        full_name="Inactive",
        hashed_password=_HASHED_PASSWORD,
        is_active=False,
        is_superuser=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    platform_session.add(user)
    await platform_session.flush()
    return user


def _make_service(db, key_service, redis=None) -> PlatformAuthService:
    return PlatformAuthService(db=db, key_service=key_service, redis=redis)


# ── login ─────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_login_returns_token_response(platform_session, mock_key_service, active_user):
    svc = _make_service(platform_session, mock_key_service)
    response = await svc.login(
        email=active_user.email,
        password=_PASSWORD,
        user_agent="pytest/1.0",
        ip_address="127.0.0.1",
    )
    assert response.access_token
    assert response.refresh_token
    assert response.token_type == "bearer"
    assert response.expires_in > 0


@pytest.mark.anyio
async def test_login_access_token_contains_expected_claims(
    platform_session, mock_key_service, rsa_keypair, active_user
):
    import jwt as pyjwt

    _, public_pem = rsa_keypair
    svc = _make_service(platform_session, mock_key_service)
    response = await svc.login(
        email=active_user.email, password=_PASSWORD,
        user_agent=None, ip_address=None,
    )
    claims = pyjwt.decode(
        response.access_token,
        public_pem,
        algorithms=["RS256"],
        audience="platform",
    )
    assert claims["sub"] == str(active_user.id)
    assert claims["aud"] == "platform"
    assert claims["actor_type"] == "platform_user"
    assert "session_id" in claims
    assert "exp" in claims


@pytest.mark.anyio
async def test_login_wrong_password_raises_401(platform_session, mock_key_service, active_user):
    from fastapi import HTTPException

    svc = _make_service(platform_session, mock_key_service)
    with pytest.raises(HTTPException) as exc_info:
        await svc.login(
            email=active_user.email,
            password="WrongPassword!!!!",
            user_agent=None,
            ip_address=None,
        )
    assert exc_info.value.status_code == 401


@pytest.mark.anyio
async def test_login_unknown_email_raises_401(platform_session, mock_key_service):
    from fastapi import HTTPException

    svc = _make_service(platform_session, mock_key_service)
    with pytest.raises(HTTPException) as exc_info:
        await svc.login(
            email="nobody@example.com",
            password=_PASSWORD,
            user_agent=None,
            ip_address=None,
        )
    assert exc_info.value.status_code == 401


@pytest.mark.anyio
async def test_login_inactive_user_raises_401(platform_session, mock_key_service, inactive_user):
    from fastapi import HTTPException

    svc = _make_service(platform_session, mock_key_service)
    with pytest.raises(HTTPException) as exc_info:
        await svc.login(
            email=inactive_user.email,
            password=_PASSWORD,
            user_agent=None,
            ip_address=None,
        )
    assert exc_info.value.status_code == 401


# ── refresh ───────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_refresh_returns_new_access_token(platform_session, mock_key_service, active_user):
    svc = _make_service(platform_session, mock_key_service)
    login_resp = await svc.login(
        email=active_user.email, password=_PASSWORD,
        user_agent=None, ip_address=None,
    )
    refresh_resp = await svc.refresh(login_resp.refresh_token)

    assert refresh_resp.access_token
    assert refresh_resp.access_token != login_resp.access_token
    # refresh endpoint does not issue a new refresh token
    assert refresh_resp.refresh_token is None
    assert refresh_resp.token_type == "bearer"


@pytest.mark.anyio
async def test_refresh_with_garbage_token_raises_401(platform_session, mock_key_service):
    from fastapi import HTTPException

    svc = _make_service(platform_session, mock_key_service)
    with pytest.raises(HTTPException) as exc_info:
        await svc.refresh("not.a.valid.jwt")
    assert exc_info.value.status_code == 401


@pytest.mark.anyio
async def test_refresh_after_logout_raises_401(platform_session, mock_key_service, active_user):
    """After logout the session is revoked; refresh must reject the token."""
    from fastapi import HTTPException

    svc = _make_service(platform_session, mock_key_service)
    login_resp = await svc.login(
        email=active_user.email, password=_PASSWORD,
        user_agent=None, ip_address=None,
    )
    await svc.logout(login_resp.access_token)

    with pytest.raises(HTTPException) as exc_info:
        await svc.refresh(login_resp.refresh_token)
    assert exc_info.value.status_code == 401


# ── logout ────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_logout_revokes_session(platform_session, mock_key_service, active_user):
    """logout() must not raise — session revocation is verified via refresh test above."""
    svc = _make_service(platform_session, mock_key_service)
    login_resp = await svc.login(
        email=active_user.email, password=_PASSWORD,
        user_agent=None, ip_address=None,
    )
    # Should complete without exception
    await svc.logout(login_resp.access_token)


@pytest.mark.anyio
async def test_logout_with_invalid_token_raises_401(platform_session, mock_key_service):
    from fastapi import HTTPException

    svc = _make_service(platform_session, mock_key_service)
    with pytest.raises(HTTPException) as exc_info:
        await svc.logout("not.a.valid.jwt")
    assert exc_info.value.status_code == 401
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/iam/platform_auth/test_platform_auth_service.py -v
```

Expected: `ImportError` — `platform_auth/service.py` does not exist yet

- [ ] **Step 3: Create `app/modules/iam/platform_auth/service.py`**

```python
"""PlatformAuthService — login, refresh, and logout for platform users.

Each method is intentionally stateless between calls (no cached user objects).
Lockout tracking (Plan 10) and audit events (Plan 11) will be added as
in-place modifications to login(), refresh(), and logout() respectively.

The service receives a DB session scoped to the platform schema, a KeyService
(for signing/verification key lookups), and an optional Redis client (passed
through to SessionService for O(1) jti revocation checks).

Plans that modify this file later:
- Plan 10: lockout.record_attempt() / lockout.is_locked() calls in login()
- Plan 11: structlog audit event calls in login(), refresh(), logout()
- Plan 07: add me() method
- Plan 08: add reset_request() and reset_confirm() methods
"""
from __future__ import annotations

import uuid

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.iam.passwords.service import hash_password, needs_rehash, verify_password
from app.modules.iam.platform_auth.schemas import PlatformTokenResponse
from app.modules.iam.sessions.models import PlatformSession
from app.modules.iam.sessions.service import SessionService
from app.modules.iam.tokens.service import (
    decode_token,
    encode_access_token,
    encode_refresh_token,
)
from app.platform_.models import PlatformUser

_log = structlog.get_logger(__name__)

_AUDIENCE = "platform"


class PlatformAuthService:
    """Orchestrates platform user authentication.

    Args:
        db:          SQLAlchemy async session bound to the platform schema.
        key_service: KeyService instance for signing and verification key lookups.
        redis:       Optional Redis async client. When present, jti lookups are
                     O(1) Redis GETs; when absent (tests), falls back to DB query.
    """

    def __init__(
        self,
        db: AsyncSession,
        key_service: object,  # KeyService — typed as object to avoid circular import
        redis: object | None = None,
    ) -> None:
        self._db = db
        self._key_service = key_service
        self._redis = redis
        self._session_svc = SessionService(
            db=db,
            model_cls=PlatformSession,
            redis=redis,
        )

    # ── login ─────────────────────────────────────────────────────────────

    async def login(
        self,
        email: str,
        password: str,
        user_agent: str | None,
        ip_address: str | None,
    ) -> PlatformTokenResponse:
        """Full login flow: verify credentials → create session → issue tokens.

        Raises:
            HTTPException 401: unknown email, wrong password, or inactive user.
        """
        settings = get_settings()

        # 1. Look up user — generic 401 for both unknown and inactive to
        #    prevent user enumeration. Plan 10 adds lockout.record_attempt()
        #    calls here.
        result = await self._db.execute(
            select(PlatformUser).where(PlatformUser.email == email)
        )
        user = result.scalar_one_or_none()

        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # 2. Verify password. Plan 10 will add is_locked() check before this.
        if not user.hashed_password or not verify_password(password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # 3. Transparent rehash — upgrade argon2id parameters if needed.
        if needs_rehash(user.hashed_password):
            user.hashed_password = hash_password(password)
            # No explicit flush — committed with the session row below.

        # 4. Fetch active signing key for this audience.
        kid, private_key, algorithm = await self._key_service.get_active_signing_key(
            _AUDIENCE
        )

        # 5. Pre-generate JTI so the same value lands on the session row and
        #    inside the refresh token's claims.
        jti = str(uuid.uuid4())

        # 6. Create session row (also writes jti to Redis if redis is set).
        session_row = await self._session_svc.create(
            user_id=user.id,
            jti=jti,
            user_agent=user_agent,
            ip_address=ip_address,
            refresh_ttl_seconds=settings.jwt_refresh_ttl_platform_seconds,
        )

        # 7. Issue tokens.
        access_ttl = settings.jwt_access_ttl_seconds
        access_token = encode_access_token(
            sub=str(user.id),
            audience=_AUDIENCE,
            session_id=str(session_row.id),
            actor_type="platform_user",
            kid=kid,
            private_key=private_key,
            algorithm=algorithm,
            ttl=access_ttl,
        )
        refresh_token = encode_refresh_token(
            sub=str(user.id),
            audience=_AUDIENCE,
            session_id=str(session_row.id),
            jti=jti,
            kid=kid,
            private_key=private_key,
            algorithm=algorithm,
            ttl=settings.jwt_refresh_ttl_platform_seconds,
        )

        # Plan 11 adds: audit("platform_auth.login_success", user_id=user.id)
        # Plan 10 adds: lockout.reset(email) after successful login

        _log.info("platform_auth.login_success", user_id=str(user.id))
        return PlatformTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=access_ttl,
        )

    # ── refresh ───────────────────────────────────────────────────────────

    async def refresh(self, refresh_token: str) -> PlatformTokenResponse:
        """Issue a new access token from a valid, non-revoked refresh token.

        Does NOT rotate the refresh token — the same session stays active.

        Raises:
            HTTPException 401: malformed token, invalid signature, expired token,
                               or revoked/expired session.
        """
        settings = get_settings()

        # 1. Decode and validate the refresh token (signature + expiry + audience).
        try:
            claims = await decode_token(
                token=refresh_token,
                audience=_AUDIENCE,
                key_service=self._key_service,
            )
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

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
            _AUDIENCE
        )
        access_ttl = settings.jwt_access_ttl_seconds
        access_token = encode_access_token(
            sub=claims["sub"],
            audience=_AUDIENCE,
            session_id=session_id_str,
            actor_type="platform_user",
            kid=kid,
            private_key=private_key,
            algorithm=algorithm,
            ttl=access_ttl,
        )

        # 6. Update last_used_at on the session row.
        await self._session_svc.update_last_used(session_id)

        # Plan 11 adds: audit("platform_auth.refresh", session_id=session_id_str)

        _log.info("platform_auth.refresh", session_id=session_id_str)
        return PlatformTokenResponse(
            access_token=access_token,
            refresh_token=None,
            expires_in=access_ttl,
        )

    # ── logout ────────────────────────────────────────────────────────────

    async def logout(self, access_token: str) -> None:
        """Revoke the session associated with the given access token.

        The access token must still be valid (not expired). If the client's
        access token has already expired they should call /refresh first, or
        accept that the session will be cleaned up by the expiry beat job.

        Raises:
            HTTPException 401: malformed or invalid access token.
        """
        try:
            claims = await decode_token(
                token=access_token,
                audience=_AUDIENCE,
                key_service=self._key_service,
            )
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid or expired access token")

        session_id_str = claims.get("session_id")
        if not session_id_str:
            raise HTTPException(status_code=401, detail="Malformed token claims")

        try:
            session_id = uuid.UUID(session_id_str)
        except ValueError:
            raise HTTPException(status_code=401, detail="Malformed session_id claim")

        await self._session_svc.revoke(session_id)

        # Plan 11 adds: audit("platform_auth.logout", session_id=session_id_str)

        _log.info("platform_auth.logout", session_id=session_id_str)
```

> **Note on `decode_token` async/sync:** If `decode_token` in `tokens/service.py` is a synchronous function (it doesn't hit the DB — it only calls `key_service.get_verification_key` which is async), you may need to adjust the `await` calls. If `decode_token` is async, use `await`; if it's sync but calls an async helper internally, make it async. Check the implementation from Plan 01 and match accordingly. The pattern above assumes `decode_token` is `async def`.

> **Note on `SessionService.update_last_used`:** If Plan 03 did not implement `update_last_used(session_id)`, add it to `app/modules/iam/sessions/service.py` now:
>
> ```python
> async def update_last_used(self, session_id: uuid.UUID) -> None:
>     from datetime import UTC, datetime
>     from sqlalchemy import update
>     await self._db.execute(
>         update(self._model_cls)
>         .where(self._model_cls.id == session_id)
>         .values(last_used_at=datetime.now(UTC))
>     )
> ```

- [ ] **Step 4: Run service tests to confirm pass**

```bash
pytest tests/modules/iam/platform_auth/test_platform_auth_service.py -v
```

Expected: all 11 tests PASS. Total time ~8–12 s (argon2id hash calls).

- [ ] **Step 5: Commit**

```bash
git add app/modules/iam/platform_auth/service.py \
        tests/modules/iam/platform_auth/test_platform_auth_service.py
git commit -m "feat(iam): PlatformAuthService — login, refresh, logout"
```

---

### Task 3: Platform auth API router

**Files:**
- Create: `app/modules/iam/platform_auth/api.py`
- Create: `tests/modules/iam/platform_auth/test_platform_auth_api.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write the failing API tests**

```python
# tests/modules/iam/platform_auth/test_platform_auth_api.py
"""HTTP-level tests for /platform/auth/* endpoints.

Uses FastAPI's dependency_overrides to inject a fake PlatformAuthService so
tests do not need a real DB or real RSA keys. This verifies routing, HTTP
status codes, and response shapes — not the internal auth logic (covered by
test_platform_auth_service.py).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

from app.main import app
from app.modules.iam.platform_auth.schemas import PlatformTokenResponse


# ── Helpers ────────────────────────────────────────────────────────────────────


def _ok_token_response(*, with_refresh: bool = True) -> PlatformTokenResponse:
    return PlatformTokenResponse(
        access_token="access.token.here",
        refresh_token="refresh.token.here" if with_refresh else None,
        expires_in=900,
    )


# ── /platform/auth/token ──────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_login_returns_200_with_tokens():
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    mock_svc = AsyncMock()
    mock_svc.login = AsyncMock(return_value=_ok_token_response())

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/platform/auth/token",
                json={"email": "user@example.com", "password": "supersecret123"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["access_token"] == "access.token.here"
        assert body["refresh_token"] == "refresh.token.here"
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 900
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


@pytest.mark.anyio
async def test_login_returns_401_on_invalid_credentials():
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    mock_svc = AsyncMock()
    mock_svc.login = AsyncMock(
        side_effect=HTTPException(status_code=401, detail="Invalid credentials")
    )

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/platform/auth/token",
                json={"email": "nobody@example.com", "password": "wrong"},
            )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


@pytest.mark.anyio
async def test_login_returns_422_for_missing_fields():
    """FastAPI validates the request body schema — no service call needed."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/platform/auth/token", json={})
    assert resp.status_code == 422


# ── /platform/auth/refresh ────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_refresh_returns_200_with_new_access_token():
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    mock_svc = AsyncMock()
    mock_svc.refresh = AsyncMock(return_value=_ok_token_response(with_refresh=False))

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/platform/auth/refresh",
                json={"refresh_token": "some.refresh.token"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["access_token"] == "access.token.here"
        assert body["refresh_token"] is None
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


@pytest.mark.anyio
async def test_refresh_returns_401_for_invalid_token():
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    mock_svc = AsyncMock()
    mock_svc.refresh = AsyncMock(
        side_effect=HTTPException(status_code=401, detail="Invalid or expired refresh token")
    )

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/platform/auth/refresh",
                json={"refresh_token": "garbage"},
            )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


# ── /platform/auth/logout ─────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_logout_returns_204():
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    mock_svc = AsyncMock()
    mock_svc.logout = AsyncMock(return_value=None)

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/platform/auth/logout",
                headers={"Authorization": "Bearer some.valid.access.token"},
            )
        assert resp.status_code == 204
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


@pytest.mark.anyio
async def test_logout_returns_401_without_bearer_header():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/platform/auth/logout")
    # FastAPI HTTPBearer returns 403 when the header is absent
    assert resp.status_code in (401, 403)


@pytest.mark.anyio
async def test_logout_returns_401_for_invalid_token():
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    mock_svc = AsyncMock()
    mock_svc.logout = AsyncMock(
        side_effect=HTTPException(status_code=401, detail="Invalid or expired access token")
    )

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/platform/auth/logout",
                headers={"Authorization": "Bearer invalid.token"},
            )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/iam/platform_auth/test_platform_auth_api.py -v
```

Expected: `ImportError` — `platform_auth/api.py` does not exist yet, or 404s if the router is not wired

- [ ] **Step 3: Create `app/modules/iam/platform_auth/api.py`**

```python
"""FastAPI router for /platform/auth/* endpoints.

Three endpoints in this file:
  POST /platform/auth/token   — login (no auth required)
  POST /platform/auth/refresh — exchange refresh token for new access token (no auth)
  POST /platform/auth/logout  — revoke session (Bearer access token required)

GET /platform/auth/me is added in Plan 07.
Password reset endpoints are added in Plan 08.
"""
from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.db import get_platform_session
from app.modules.iam.keys.service import KeyService
from app.modules.iam.platform_auth.schemas import (
    PlatformLoginRequest,
    PlatformRefreshRequest,
    PlatformTokenResponse,
)
from app.modules.iam.platform_auth.service import PlatformAuthService

router = APIRouter(prefix="/platform/auth", tags=["platform-auth"])
_log = structlog.get_logger(__name__)
_bearer = HTTPBearer()


async def get_platform_auth_service(
    request: Request,
    session: Annotated[object, Depends(get_platform_session)],
) -> PlatformAuthService:
    """FastAPI dependency that constructs a PlatformAuthService per request.

    Redis is pulled from app.state.redis (set in lifespan). If Redis is not
    configured on app state, falls back to None — SessionService handles that
    gracefully with a DB fallback for jti checks.
    """
    redis = getattr(request.app.state, "redis", None)
    key_service = KeyService(db=session)
    return PlatformAuthService(db=session, key_service=key_service, redis=redis)


PlatformAuth = Annotated[PlatformAuthService, Depends(get_platform_auth_service)]


@router.post("/token", response_model=PlatformTokenResponse)
async def platform_login(
    body: PlatformLoginRequest,
    request: Request,
    svc: PlatformAuth,
) -> PlatformTokenResponse:
    """Exchange email + password for an access token and refresh token."""
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    return await svc.login(
        email=body.email,
        password=body.password,
        user_agent=user_agent,
        ip_address=ip_address,
    )


@router.post("/refresh", response_model=PlatformTokenResponse)
async def platform_refresh(
    body: PlatformRefreshRequest,
    svc: PlatformAuth,
) -> PlatformTokenResponse:
    """Exchange a valid refresh token for a new access token."""
    return await svc.refresh(body.refresh_token)


@router.post("/logout", status_code=204)
async def platform_logout(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    svc: PlatformAuth,
) -> Response:
    """Revoke the session associated with the provided Bearer access token."""
    await svc.logout(credentials.credentials)
    return Response(status_code=204)
```

- [ ] **Step 4: Wire the router into `app/main.py`**

Add the import and `app.include_router()` call alongside the existing platform routers:

```python
from app.modules.iam.platform_auth.api import router as platform_auth_router
```

Then add inside the module body (after the existing `include_router` calls):

```python
app.include_router(platform_auth_router)
```

The relevant section of `main.py` after the edit should look like:

```python
from app.modules.maker_checker.api import router as maker_checker_router
from app.modules.iam.platform_auth.api import router as platform_auth_router
from app.platform_.tenants.api import router as platform_tenants_router
from app.platform_.users.api import router as platform_users_router

# ... (logging setup, lifespan, app = FastAPI(...), middleware) ...

app.include_router(maker_checker_router)
app.include_router(platform_auth_router)
app.include_router(platform_tenants_router)
app.include_router(platform_users_router)
```

- [ ] **Step 5: Run API tests to confirm pass**

```bash
pytest tests/modules/iam/platform_auth/test_platform_auth_api.py -v
```

Expected: all 8 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/modules/iam/platform_auth/api.py \
        tests/modules/iam/platform_auth/test_platform_auth_api.py \
        app/main.py
git commit -m "feat(iam): /platform/auth/token, /refresh, /logout endpoints"
```

---

## Verification Criteria

Before marking this plan complete, run the following in order:

```bash
# 1. Linting — zero errors
ruff check app/modules/iam/platform_auth/ app/modules/iam/tokens/service.py

# 2. Type checking — zero errors
mypy app/modules/iam/platform_auth/ app/modules/iam/tokens/service.py --strict

# 3. Service tests (argon2id — ~8–12 s)
pytest tests/modules/iam/platform_auth/test_platform_auth_service.py -v

# 4. API tests (fast — mocked service)
pytest tests/modules/iam/platform_auth/test_platform_auth_api.py -v

# 5. Token service regression (encode_refresh_token signature change)
pytest tests/modules/iam/tokens/ -v

# 6. Full suite — no regressions
pytest tests/ -v
```

All commands must exit cleanly (zero failures, zero errors) before this plan is considered complete.

---

## What is NOT in this plan

- **`GET /platform/auth/me`** — added in Plan 07, in this same `api.py` file and a new `me()` method on `PlatformAuthService`.
- **Password reset endpoints** — added in Plan 08.
- **Account lockout** (failed-attempt tracking, 423 responses) — added in Plan 10. Plan 10 modifies `login()` in `service.py` to call `lockout.record_attempt()` and `lockout.is_locked()`.
- **Audit events** (`platform_auth.login_success`, `platform_auth.refresh`, `platform_auth.logout`) — added in Plan 11. Plan 11 inserts `structlog` audit calls inside these same methods.
- **Real JWT-validating `get_current_platform_user`** — replaced in Plan 09. Plan 09 updates `app/platform_/auth.py` to call `decode_token` and `SessionService.get_by_session_id`.
