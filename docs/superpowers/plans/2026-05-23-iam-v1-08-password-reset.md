# IAM v1-08: Password Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `POST /platform/auth/password-reset/request`, `/confirm`, and their tenant equivalents (`POST /auth/password-reset/request`, `/confirm`). A shared HMAC-SHA256 token module provides tamper-proof, time-limited reset tokens. JTIs are stored in Redis for single-use enforcement.

**Architecture:** A standalone utility module `app/modules/iam/reset_tokens.py` encapsulates HMAC token generation and verification — no FastAPI, no DB, no Redis, pure Python. Both `PlatformAuthService` and `TenantAuthService` gain `reset_request()` and `reset_confirm()` methods that import from this module. The request endpoint always returns 204 regardless of whether the email exists (prevents user enumeration). The confirm endpoint verifies the token, consumes the Redis JTI, hashes the new password, and revokes all existing sessions. When Redis is absent (test environments), JTI consumption is skipped — tests still exercise the core hash-and-revoke path. The notifier is a structlog warning in v1; the design comment points to where email would be wired in.

**Tech Stack:** Python `hmac` + `hashlib` (stdlib), SQLAlchemy 2.0 async, redis-py async, passlib argon2id, pytest-anyio

---

## Required Reading (complete before starting any task)

1. `CLAUDE.md` — architectural rules
2. `docs/superpowers/specs/2026-05-21-iam-v1-design.md` §7.1 (password reset request + confirm for platform), §7.2 (same for tenant)
3. `app/core/config.py` — `app_secret_key` (HMAC signing key for reset tokens)
4. `app/modules/iam/platform_auth/service.py` — `PlatformAuthService` (add methods here)
5. `app/modules/iam/platform_auth/api.py` — existing platform auth router (add routes here)
6. `app/modules/iam/tenant_auth/service.py` — `TenantAuthService` (add methods here)
7. `app/modules/iam/tenant_auth/api.py` — existing tenant auth router (add routes here)
8. `app/modules/iam/sessions/service.py` — `SessionService.revoke_all_for_user()` (Plan 03)
9. `app/modules/iam/passwords/service.py` — `hash_password` raises `ValueError` if too short (Plan 02)
10. `tests/conftest.py` — `platform_session`, `tenant_session`, `anyio_backend` fixtures

---

## Prerequisite Check: `SessionService.revoke_all_for_user`

Before starting Task 3, verify that `app/modules/iam/sessions/service.py` has a `revoke_all_for_user(user_id: uuid.UUID) -> None` method. If Plan 03 did not include it, add it now:

```python
async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
    """Bulk-revoke all non-revoked sessions for the given user.

    Called on password change / admin revocation. Does not delete Redis
    keys individually — the DB revoked_at column is authoritative for
    revocation; Redis keys will expire naturally within their TTL.
    """
    from datetime import UTC, datetime
    from sqlalchemy import update

    # Determine the user-ID column name by inspecting the model class.
    if hasattr(self._model_cls, "platform_user_id"):
        user_col = self._model_cls.platform_user_id
    else:
        user_col = self._model_cls.tenant_user_id

    await self._db.execute(
        update(self._model_cls)
        .where(user_col == user_id)
        .where(self._model_cls.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
```

Run existing session tests to confirm no regressions:

```bash
pytest tests/modules/iam/sessions/ -v
```

---

## File Map

```
CREATE app/modules/iam/reset_tokens.py                    — make_reset_token, verify_reset_token
CREATE tests/modules/iam/test_reset_tokens.py             — unit tests for HMAC helpers
MODIFY app/modules/iam/platform_auth/schemas.py           — add PlatformPasswordResetRequestBody, PlatformPasswordResetConfirmBody
MODIFY app/modules/iam/platform_auth/service.py           — add reset_request(), reset_confirm()
MODIFY app/modules/iam/platform_auth/api.py               — add /platform/auth/password-reset/* routes
MODIFY app/modules/iam/tenant_auth/schemas.py             — add TenantPasswordResetRequestBody, TenantPasswordResetConfirmBody
MODIFY app/modules/iam/tenant_auth/service.py             — add reset_request(), reset_confirm()
MODIFY app/modules/iam/tenant_auth/api.py                 — add /auth/password-reset/* routes
MODIFY tests/modules/iam/platform_auth/test_platform_auth_service.py  — append reset tests
MODIFY tests/modules/iam/platform_auth/test_platform_auth_api.py      — append reset API tests
MODIFY tests/modules/iam/tenant_auth/test_tenant_auth_service.py      — append reset tests
MODIFY tests/modules/iam/tenant_auth/test_tenant_auth_api.py          — append reset API tests
```

---

### Task 1: HMAC reset token helpers

**Files:**
- Create: `app/modules/iam/reset_tokens.py`
- Create: `tests/modules/iam/test_reset_tokens.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/modules/iam/test_reset_tokens.py
"""Unit tests for HMAC-SHA256 password reset token helpers.

No DB, no Redis, no async — these are pure synchronous functions.
"""
import time

import pytest

from app.modules.iam.reset_tokens import make_reset_token, verify_reset_token


def test_make_and_verify_round_trip():
    token, jti = make_reset_token("user-id-abc", "test-secret")
    payload = verify_reset_token(token, "test-secret")
    assert payload["sub"] == "user-id-abc"
    assert payload["jti"] == jti
    assert payload["type"] == "password_reset"


def test_jti_is_unique_per_call():
    _, jti1 = make_reset_token("user-id", "secret")
    _, jti2 = make_reset_token("user-id", "secret")
    assert jti1 != jti2


def test_wrong_secret_raises_value_error():
    token, _ = make_reset_token("user-id-abc", "correct-secret")
    with pytest.raises(ValueError, match="invalid token signature"):
        verify_reset_token(token, "wrong-secret")


def test_expired_token_raises_value_error():
    # ttl=-1 puts exp in the past.
    token, _ = make_reset_token("user-id-abc", "secret", ttl=-1)
    with pytest.raises(ValueError, match="token has expired"):
        verify_reset_token(token, "secret")


def test_tampered_signature_raises_value_error():
    token, _ = make_reset_token("user-id-abc", "secret")
    # Replace last 8 chars of signature with garbage.
    tampered = token[:-8] + "xxxxxxxx"
    with pytest.raises(ValueError, match="invalid token signature"):
        verify_reset_token(tampered, "secret")


def test_malformed_token_missing_dot_raises_value_error():
    with pytest.raises(ValueError, match="malformed token"):
        verify_reset_token("nodothere", "secret")


def test_wrong_token_type_raises_value_error():
    """A JWT or other token that happens to be valid HMAC must still be rejected."""
    import base64
    import hashlib
    import hmac
    import json

    payload = {"sub": "x", "jti": "y", "exp": int(time.time()) + 900, "type": "access"}
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).rstrip(b"=").decode()
    sig = hmac.new("secret".encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    token = f"{payload_b64}.{sig}"
    with pytest.raises(ValueError, match="wrong token type"):
        verify_reset_token(token, "secret")


def test_make_reset_token_returns_string():
    token, jti = make_reset_token("uid", "s")
    assert isinstance(token, str)
    assert isinstance(jti, str)
    assert "." in token  # payload.signature
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/iam/test_reset_tokens.py -v
```

Expected: `ImportError` — `reset_tokens.py` does not exist yet

- [ ] **Step 3: Create `app/modules/iam/reset_tokens.py`**

```python
"""HMAC-SHA256 signed password reset tokens.

Token format (URL-safe string):
    <base64url-payload>.<hex-hmac-signature>

Payload JSON fields:
    sub   : str  — user ID (UUID string)
    jti   : str  — unique token ID; caller stores in Redis for one-use enforcement
    exp   : int  — Unix timestamp of expiry
    type  : str  — always "password_reset" (rejects tokens issued for other purposes)

The signing key is passed explicitly so both platform and tenant callers can
use the same secret (settings.app_secret_key) or different ones if needed.

Redis tracking is NOT handled here — this module only creates and verifies
tokens. The caller is responsible for:
  1. After make_reset_token: SET iam:pwreset:{jti} "1" EX <ttl> in Redis.
  2. Before consuming: EXISTS iam:pwreset:{jti} → reject if 0.
  3. After confirming: DEL iam:pwreset:{jti} in Redis.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid

_RESET_TTL_SECONDS = 900  # 15 minutes


def make_reset_token(
    user_id: str,
    secret: str,
    ttl: int = _RESET_TTL_SECONDS,
) -> tuple[str, str]:
    """Create a signed password reset token.

    Args:
        user_id: UUID string of the user requesting the reset.
        secret:  HMAC signing key (use settings.app_secret_key).
        ttl:     Lifetime in seconds. Defaults to 900 (15 minutes).

    Returns:
        (token, jti) — ``token`` is the opaque string to deliver to the user
        (via email or log); ``jti`` is the unique token ID the caller stores
        in Redis with ``EX ttl``.
    """
    jti = str(uuid.uuid4())
    payload = {
        "sub": user_id,
        "jti": jti,
        "exp": int(time.time()) + ttl,
        "type": "password_reset",
    }
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .rstrip(b"=")
        .decode()
    )
    sig = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}", jti


def verify_reset_token(token: str, secret: str) -> dict[str, str | int]:
    """Verify a signed reset token and return its payload.

    Args:
        token:  The opaque token string returned by ``make_reset_token``.
        secret: HMAC signing key — must match the one used to create the token.

    Returns:
        Payload dict with keys: ``sub``, ``jti``, ``exp``, ``type``.

    Raises:
        ValueError: token is malformed, signature is invalid, token has
                    expired, or token type is not "password_reset".
    """
    parts = token.split(".", 1)
    if len(parts) != 2:
        raise ValueError("malformed token: missing signature separator")
    payload_b64, sig = parts

    expected_sig = hmac.new(
        secret.encode(), payload_b64.encode(), hashlib.sha256
    ).hexdigest()
    # Constant-time comparison prevents timing attacks.
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("invalid token signature")

    # Restore base64 padding before decoding.
    rem = len(payload_b64) % 4
    if rem:
        payload_b64 += "=" * (4 - rem)

    try:
        payload: dict[str, str | int] = json.loads(
            base64.urlsafe_b64decode(payload_b64)
        )
    except Exception as exc:
        raise ValueError("malformed token payload") from exc

    if payload.get("type") != "password_reset":
        raise ValueError("wrong token type")

    if int(payload["exp"]) < int(time.time()):
        raise ValueError("token has expired")

    return payload
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
pytest tests/modules/iam/test_reset_tokens.py -v
```

Expected: 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/modules/iam/reset_tokens.py tests/modules/iam/test_reset_tokens.py
git commit -m "feat(iam): HMAC-SHA256 reset token helpers — make_reset_token, verify_reset_token"
```

---

### Task 2: Password reset schemas

**Files:**
- Modify: `app/modules/iam/platform_auth/schemas.py`
- Modify: `app/modules/iam/tenant_auth/schemas.py`

No dedicated test needed — schemas are validated by the API tests in Tasks 4 and 6.

- [ ] **Step 1: Append reset schemas to `app/modules/iam/platform_auth/schemas.py`**

Add after the existing `PlatformTokenResponse` class:

```python
class PlatformPasswordResetRequestBody(BaseModel):
    email: EmailStr


class PlatformPasswordResetConfirmBody(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=1)
    # Note: hash_password() enforces the real minimum length (settings.auth_password_min_length).
    # A Pydantic min_length=1 here only catches completely empty strings.
```

- [ ] **Step 2: Append reset schemas to `app/modules/iam/tenant_auth/schemas.py`**

Add after the existing `TenantUserOut` class:

```python
class TenantPasswordResetRequestBody(BaseModel):
    email: EmailStr


class TenantPasswordResetConfirmBody(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=1)
```

> `EmailStr` is already imported in both files. `Field` is already imported in both files.

- [ ] **Step 3: Verify schemas parse cleanly**

```bash
python -c "
from app.modules.iam.platform_auth.schemas import (
    PlatformPasswordResetRequestBody, PlatformPasswordResetConfirmBody
)
from app.modules.iam.tenant_auth.schemas import (
    TenantPasswordResetRequestBody, TenantPasswordResetConfirmBody
)
r1 = PlatformPasswordResetRequestBody(email='user@example.com')
r2 = PlatformPasswordResetConfirmBody(token='tok', new_password='newpass')
r3 = TenantPasswordResetRequestBody(email='member@sacco.org')
r4 = TenantPasswordResetConfirmBody(token='tok', new_password='newpass')
print('reset schemas OK')
"
```

Expected: `reset schemas OK`

- [ ] **Step 4: Commit**

```bash
git add app/modules/iam/platform_auth/schemas.py app/modules/iam/tenant_auth/schemas.py
git commit -m "feat(iam): password reset request/confirm Pydantic schemas"
```

---

### Task 3: `PlatformAuthService` — `reset_request()` and `reset_confirm()`

**Files:**
- Modify: `app/modules/iam/platform_auth/service.py`
- Modify: `tests/modules/iam/platform_auth/test_platform_auth_service.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/modules/iam/platform_auth/test_platform_auth_service.py`:

```python
# ── reset_request ─────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_reset_request_returns_none_for_known_email(
    platform_session, mock_key_service, active_user
):
    """reset_request() must not raise for a known email."""
    svc = _make_service(platform_session, mock_key_service)
    result = await svc.reset_request(email=active_user.email)
    assert result is None


@pytest.mark.anyio
async def test_reset_request_returns_none_for_unknown_email(
    platform_session, mock_key_service
):
    """reset_request() must not raise for unknown emails — prevents enumeration."""
    svc = _make_service(platform_session, mock_key_service)
    result = await svc.reset_request(email="nobody@nowhere.com")
    assert result is None


# ── reset_confirm ─────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_reset_confirm_changes_password(
    platform_session, mock_key_service, active_user
):
    from app.modules.iam.reset_tokens import make_reset_token
    from app.core.config import get_settings

    svc = _make_service(platform_session, mock_key_service)
    token, _jti = make_reset_token(str(active_user.id), get_settings().app_secret_key)

    new_password = "NewSecurePassword123!"
    await svc.reset_confirm(token=token, new_password=new_password)

    # The password hash must have changed.
    await platform_session.refresh(active_user)
    from app.modules.iam.passwords.service import verify_password
    assert verify_password(new_password, active_user.hashed_password) is True


@pytest.mark.anyio
async def test_reset_confirm_revokes_existing_sessions(
    platform_session, mock_key_service, active_user
):
    from datetime import UTC, datetime
    from sqlalchemy import select
    from app.modules.iam.reset_tokens import make_reset_token
    from app.modules.iam.sessions.models import PlatformSession
    from app.core.config import get_settings

    # Create an active session first.
    svc = _make_service(platform_session, mock_key_service)
    login_resp = await svc.login(
        email=active_user.email, password=_PASSWORD,
        user_agent=None, ip_address=None,
    )
    # Confirm there is at least one non-revoked session.
    result = await platform_session.execute(
        select(PlatformSession).where(
            PlatformSession.platform_user_id == active_user.id,
            PlatformSession.revoked_at.is_(None),
        )
    )
    assert result.scalar_one_or_none() is not None

    # Reset password.
    token, _jti = make_reset_token(str(active_user.id), get_settings().app_secret_key)
    await svc.reset_confirm(token=token, new_password="BrandNewPassword456!")

    # The session must now be revoked.
    await platform_session.refresh(
        await platform_session.get(PlatformSession, result.scalar_one().id)
        if hasattr(result, "scalar_one") else None
    )
    result2 = await platform_session.execute(
        select(PlatformSession).where(
            PlatformSession.platform_user_id == active_user.id,
            PlatformSession.revoked_at.is_(None),
        )
    )
    assert result2.scalar_one_or_none() is None


@pytest.mark.anyio
async def test_reset_confirm_invalid_token_raises_400(
    platform_session, mock_key_service
):
    from fastapi import HTTPException

    svc = _make_service(platform_session, mock_key_service)
    with pytest.raises(HTTPException) as exc_info:
        await svc.reset_confirm(token="not.a.valid.token", new_password="NewPassword123!")
    assert exc_info.value.status_code == 400


@pytest.mark.anyio
async def test_reset_confirm_short_password_raises_400(
    platform_session, mock_key_service, active_user
):
    from fastapi import HTTPException
    from app.modules.iam.reset_tokens import make_reset_token
    from app.core.config import get_settings

    svc = _make_service(platform_session, mock_key_service)
    token, _jti = make_reset_token(str(active_user.id), get_settings().app_secret_key)
    with pytest.raises(HTTPException) as exc_info:
        await svc.reset_confirm(token=token, new_password="tooshort")
    assert exc_info.value.status_code == 400
```

> **Note on `test_reset_confirm_revokes_existing_sessions`:** This test creates a session via `login()`, which calls argon2id verify (~300 ms). Then it calls `reset_confirm()` which calls argon2id hash (~300 ms). Total: ~600 ms for this test. This is intentional and expected.

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/iam/platform_auth/test_platform_auth_service.py -v -k "reset"
```

Expected: `AttributeError` — `PlatformAuthService` has no `reset_request` or `reset_confirm` yet

- [ ] **Step 3: Add reset methods to `app/modules/iam/platform_auth/service.py`**

Add these imports at the top of the file alongside existing imports:

```python
from app.modules.iam.reset_tokens import make_reset_token, verify_reset_token
```

Then append these two methods to the `PlatformAuthService` class body, after `me()`:

```python
    # ── reset_request ─────────────────────────────────────────────────────

    async def reset_request(self, email: str) -> None:
        """Send a password reset token to the given email address.

        Always returns None — never reveals whether the email exists
        (prevents user enumeration).

        If the user exists:
          1. Generates a signed HMAC token (15-minute expiry).
          2. Stores the JTI in Redis for single-use enforcement.
          3. Logs the token to structlog (replace with email notifier in prod).

        Plan 11 adds: audit("platform_auth.password_reset_requested", ...)
        """
        settings = get_settings()

        result = await self._db.execute(
            select(PlatformUser).where(PlatformUser.email == email)
        )
        user = result.scalar_one_or_none()
        if user is None:
            # Return silently — caller gets the same 204 regardless.
            return

        token, jti = make_reset_token(str(user.id), settings.app_secret_key)

        if self._redis is not None:
            await self._redis.set(f"iam:pwreset:{jti}", "1", ex=900)

        # Production: replace this log call with an email send.
        # The notifier interface (e.g. EmailNotifier.send(user.email, token))
        # is wired in a future iteration.
        _log.warning(
            "PASSWORD RESET TOKEN — dev only, configure email notifier for production",
            email=email,
            reset_token=token,
        )

        # Plan 11 adds: audit("platform_auth.password_reset_requested", user_id=str(user.id))

    # ── reset_confirm ─────────────────────────────────────────────────────

    async def reset_confirm(self, token: str, new_password: str) -> None:
        """Confirm a password reset: validate token, set new password, revoke sessions.

        Raises:
            HTTPException 400: invalid/expired token, already-consumed JTI,
                               user not found, or new password too short.
        """
        settings = get_settings()

        # 1. Verify token signature and expiry.
        try:
            payload = verify_reset_token(token, settings.app_secret_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid reset token: {exc}")

        jti = str(payload["jti"])
        user_id_str = str(payload["sub"])

        # 2. Check Redis: token must not have been consumed already.
        if self._redis is not None:
            exists = await self._redis.exists(f"iam:pwreset:{jti}")
            if not exists:
                raise HTTPException(
                    status_code=400,
                    detail="Reset token has already been used or has expired",
                )

        try:
            user_id = uuid.UUID(user_id_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="Malformed token payload")

        # 3. Fetch user.
        result = await self._db.execute(
            select(PlatformUser).where(PlatformUser.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=400, detail="Invalid reset token")

        # 4. Hash new password — hash_password raises ValueError if too short.
        try:
            user.hashed_password = hash_password(new_password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        # 5. Consume the JTI so the token cannot be reused.
        if self._redis is not None:
            await self._redis.delete(f"iam:pwreset:{jti}")

        # 6. Revoke all active sessions — forces re-login with new password.
        await self._session_svc.revoke_all_for_user(user_id)

        # Plan 11 adds: audit("platform_auth.password_reset_confirmed", user_id=str(user.id))

        _log.info("platform_auth.password_reset_confirmed", user_id=str(user.id))
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
pytest tests/modules/iam/platform_auth/test_platform_auth_service.py -v -k "reset"
```

Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/modules/iam/platform_auth/service.py \
        tests/modules/iam/platform_auth/test_platform_auth_service.py
git commit -m "feat(iam): PlatformAuthService.reset_request() and reset_confirm()"
```

---

### Task 4: Platform auth password reset API endpoints

**Files:**
- Modify: `app/modules/iam/platform_auth/api.py`
- Modify: `tests/modules/iam/platform_auth/test_platform_auth_api.py`

- [ ] **Step 1: Write the failing API tests**

Append to `tests/modules/iam/platform_auth/test_platform_auth_api.py`:

```python
# ── /platform/auth/password-reset/request ─────────────────────────────────────


@pytest.mark.anyio
async def test_platform_reset_request_returns_204_for_known_email():
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    mock_svc = AsyncMock()
    mock_svc.reset_request = AsyncMock(return_value=None)

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/platform/auth/password-reset/request",
                json={"email": "user@example.com"},
            )
        assert resp.status_code == 204
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


@pytest.mark.anyio
async def test_platform_reset_request_returns_204_for_unknown_email():
    """Unknown emails must also return 204 — no enumeration."""
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    mock_svc = AsyncMock()
    mock_svc.reset_request = AsyncMock(return_value=None)

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/platform/auth/password-reset/request",
                json={"email": "nobody@example.com"},
            )
        assert resp.status_code == 204
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


@pytest.mark.anyio
async def test_platform_reset_request_returns_422_for_invalid_email():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/platform/auth/password-reset/request",
            json={"email": "not-an-email"},
        )
    assert resp.status_code == 422


# ── /platform/auth/password-reset/confirm ─────────────────────────────────────


@pytest.mark.anyio
async def test_platform_reset_confirm_returns_204_on_success():
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    mock_svc = AsyncMock()
    mock_svc.reset_confirm = AsyncMock(return_value=None)

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/platform/auth/password-reset/confirm",
                json={"token": "some.valid.token", "new_password": "NewSecurePass123!"},
            )
        assert resp.status_code == 204
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


@pytest.mark.anyio
async def test_platform_reset_confirm_returns_400_for_invalid_token():
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    mock_svc = AsyncMock()
    mock_svc.reset_confirm = AsyncMock(
        side_effect=HTTPException(status_code=400, detail="Invalid reset token: token has expired")
    )

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/platform/auth/password-reset/confirm",
                json={"token": "expired.token", "new_password": "NewSecurePass123!"},
            )
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


@pytest.mark.anyio
async def test_platform_reset_confirm_returns_422_for_missing_fields():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/platform/auth/password-reset/confirm",
            json={"token": "tok"},  # missing new_password
        )
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/iam/platform_auth/test_platform_auth_api.py -v -k "reset"
```

Expected: 404 — routes do not exist yet

- [ ] **Step 3: Add reset routes to `app/modules/iam/platform_auth/api.py`**

Add to the import from `platform_auth.schemas`:

```python
from app.modules.iam.platform_auth.schemas import (
    PlatformLoginRequest,
    PlatformPasswordResetConfirmBody,
    PlatformPasswordResetRequestBody,
    PlatformRefreshRequest,
    PlatformTokenResponse,
)
```

Then append these two routes after the `platform_me` route:

```python
@router.post("/password-reset/request", status_code=204)
async def platform_reset_request(
    body: PlatformPasswordResetRequestBody,
    svc: PlatformAuth,
) -> Response:
    """Request a password reset link.

    Always returns 204 — the response is identical whether or not the email
    exists in the system, preventing user enumeration.
    """
    await svc.reset_request(body.email)
    return Response(status_code=204)


@router.post("/password-reset/confirm", status_code=204)
async def platform_reset_confirm(
    body: PlatformPasswordResetConfirmBody,
    svc: PlatformAuth,
) -> Response:
    """Confirm a password reset using the token from the request email."""
    await svc.reset_confirm(token=body.token, new_password=body.new_password)
    return Response(status_code=204)
```

- [ ] **Step 4: Run all platform auth tests to confirm pass**

```bash
pytest tests/modules/iam/platform_auth/ -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/modules/iam/platform_auth/api.py \
        tests/modules/iam/platform_auth/test_platform_auth_api.py
git commit -m "feat(iam): POST /platform/auth/password-reset/request and /confirm"
```

---

### Task 5: `TenantAuthService` — `reset_request()` and `reset_confirm()`

**Files:**
- Modify: `app/modules/iam/tenant_auth/service.py`
- Modify: `tests/modules/iam/tenant_auth/test_tenant_auth_service.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/modules/iam/tenant_auth/test_tenant_auth_service.py`:

```python
# ── reset_request ─────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_tenant_reset_request_returns_none_for_known_email(
    tenant_session, mock_key_service, active_tenant_user
):
    svc = _make_service(tenant_session, mock_key_service)
    result = await svc.reset_request(email=active_tenant_user.email)
    assert result is None


@pytest.mark.anyio
async def test_tenant_reset_request_returns_none_for_unknown_email(
    tenant_session, mock_key_service
):
    svc = _make_service(tenant_session, mock_key_service)
    result = await svc.reset_request(email="ghost@nowhere.org")
    assert result is None


# ── reset_confirm ─────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_tenant_reset_confirm_changes_password(
    tenant_session, mock_key_service, active_tenant_user
):
    from app.modules.iam.reset_tokens import make_reset_token
    from app.core.config import get_settings
    from app.modules.iam.passwords.service import verify_password

    svc = _make_service(tenant_session, mock_key_service)
    token, _jti = make_reset_token(str(active_tenant_user.id), get_settings().app_secret_key)

    new_password = "NewTenantPassword789!"
    await svc.reset_confirm(token=token, new_password=new_password)

    await tenant_session.refresh(active_tenant_user)
    assert verify_password(new_password, active_tenant_user.hashed_password) is True


@pytest.mark.anyio
async def test_tenant_reset_confirm_revokes_existing_sessions(
    tenant_session, mock_key_service, active_tenant_user
):
    from sqlalchemy import select
    from app.modules.iam.reset_tokens import make_reset_token
    from app.modules.iam.sessions.models import TenantSession
    from app.core.config import get_settings

    svc = _make_service(tenant_session, mock_key_service)
    # Create an active session.
    await svc.login(
        email=active_tenant_user.email, password=_PASSWORD,
        user_agent=None, ip_address=None,
    )
    result = await tenant_session.execute(
        select(TenantSession).where(
            TenantSession.tenant_user_id == active_tenant_user.id,
            TenantSession.revoked_at.is_(None),
        )
    )
    assert result.scalar_one_or_none() is not None

    # Confirm reset.
    token, _jti = make_reset_token(str(active_tenant_user.id), get_settings().app_secret_key)
    await svc.reset_confirm(token=token, new_password="AnotherNewPassword321!")

    result2 = await tenant_session.execute(
        select(TenantSession).where(
            TenantSession.tenant_user_id == active_tenant_user.id,
            TenantSession.revoked_at.is_(None),
        )
    )
    assert result2.scalar_one_or_none() is None


@pytest.mark.anyio
async def test_tenant_reset_confirm_invalid_token_raises_400(
    tenant_session, mock_key_service
):
    from fastapi import HTTPException

    svc = _make_service(tenant_session, mock_key_service)
    with pytest.raises(HTTPException) as exc_info:
        await svc.reset_confirm(token="bad.token", new_password="NewPassword123!")
    assert exc_info.value.status_code == 400


@pytest.mark.anyio
async def test_tenant_reset_confirm_short_password_raises_400(
    tenant_session, mock_key_service, active_tenant_user
):
    from fastapi import HTTPException
    from app.modules.iam.reset_tokens import make_reset_token
    from app.core.config import get_settings

    svc = _make_service(tenant_session, mock_key_service)
    token, _jti = make_reset_token(str(active_tenant_user.id), get_settings().app_secret_key)
    with pytest.raises(HTTPException) as exc_info:
        await svc.reset_confirm(token=token, new_password="short")
    assert exc_info.value.status_code == 400
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/iam/tenant_auth/test_tenant_auth_service.py -v -k "reset"
```

Expected: `AttributeError` — `TenantAuthService` has no `reset_request` or `reset_confirm` yet

- [ ] **Step 3: Add reset methods to `app/modules/iam/tenant_auth/service.py`**

Add this import at the top alongside existing imports:

```python
from app.modules.iam.reset_tokens import make_reset_token, verify_reset_token
```

Then append these two methods to the `TenantAuthService` class body, after `me()`:

```python
    # ── reset_request ─────────────────────────────────────────────────────

    async def reset_request(self, email: str) -> None:
        """Request a password reset for a tenant user.

        Always returns None to prevent user enumeration. Identical flow to
        PlatformAuthService.reset_request() but queries TenantUser.

        Plan 11 adds: audit("tenant_auth.password_reset_requested", ...)
        """
        settings = get_settings()

        result = await self._db.execute(
            select(TenantUser).where(TenantUser.email == email)
        )
        user = result.scalar_one_or_none()
        if user is None:
            return

        token, jti = make_reset_token(str(user.id), settings.app_secret_key)

        if self._redis is not None:
            await self._redis.set(f"iam:pwreset:{jti}", "1", ex=900)

        _log.warning(
            "PASSWORD RESET TOKEN — dev only, configure email notifier for production",
            email=email,
            tenant=self._slug,
            reset_token=token,
        )

        # Plan 11 adds: audit("tenant_auth.password_reset_requested", user_id=str(user.id))

    # ── reset_confirm ─────────────────────────────────────────────────────

    async def reset_confirm(self, token: str, new_password: str) -> None:
        """Confirm a tenant user password reset.

        Raises:
            HTTPException 400: invalid/expired token, already-consumed JTI,
                               user not found, or new password too short.
        """
        settings = get_settings()

        try:
            payload = verify_reset_token(token, settings.app_secret_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid reset token: {exc}")

        jti = str(payload["jti"])
        user_id_str = str(payload["sub"])

        if self._redis is not None:
            exists = await self._redis.exists(f"iam:pwreset:{jti}")
            if not exists:
                raise HTTPException(
                    status_code=400,
                    detail="Reset token has already been used or has expired",
                )

        try:
            user_id = uuid.UUID(user_id_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="Malformed token payload")

        result = await self._db.execute(
            select(TenantUser).where(TenantUser.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=400, detail="Invalid reset token")

        try:
            user.hashed_password = hash_password(new_password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        if self._redis is not None:
            await self._redis.delete(f"iam:pwreset:{jti}")

        await self._session_svc.revoke_all_for_user(user_id)

        # Plan 11 adds: audit("tenant_auth.password_reset_confirmed", user_id=str(user.id))

        _log.info(
            "tenant_auth.password_reset_confirmed",
            user_id=str(user.id),
            tenant=self._slug,
        )
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
pytest tests/modules/iam/tenant_auth/test_tenant_auth_service.py -v -k "reset"
```

Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/modules/iam/tenant_auth/service.py \
        tests/modules/iam/tenant_auth/test_tenant_auth_service.py
git commit -m "feat(iam): TenantAuthService.reset_request() and reset_confirm()"
```

---

### Task 6: Tenant auth password reset API endpoints

**Files:**
- Modify: `app/modules/iam/tenant_auth/api.py`
- Modify: `tests/modules/iam/tenant_auth/test_tenant_auth_api.py`

- [ ] **Step 1: Write the failing API tests**

Append to `tests/modules/iam/tenant_auth/test_tenant_auth_api.py`:

```python
# ── /auth/password-reset/request ──────────────────────────────────────────────


@pytest.mark.anyio
async def test_tenant_reset_request_returns_204():
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    mock_svc = AsyncMock()
    mock_svc.reset_request = AsyncMock(return_value=None)

    app.dependency_overrides[get_tenant_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/password-reset/request",
                json={"email": "member@sacco.org"},
                headers=_SLUG_HEADER,
            )
        assert resp.status_code == 204
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)


@pytest.mark.anyio
async def test_tenant_reset_request_returns_422_for_invalid_email():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/auth/password-reset/request",
            json={"email": "bad-email"},
            headers=_SLUG_HEADER,
        )
    assert resp.status_code == 422


# ── /auth/password-reset/confirm ──────────────────────────────────────────────


@pytest.mark.anyio
async def test_tenant_reset_confirm_returns_204_on_success():
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    mock_svc = AsyncMock()
    mock_svc.reset_confirm = AsyncMock(return_value=None)

    app.dependency_overrides[get_tenant_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/password-reset/confirm",
                json={"token": "valid.tok", "new_password": "GoodPassword123!"},
                headers=_SLUG_HEADER,
            )
        assert resp.status_code == 204
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)


@pytest.mark.anyio
async def test_tenant_reset_confirm_returns_400_for_bad_token():
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    mock_svc = AsyncMock()
    mock_svc.reset_confirm = AsyncMock(
        side_effect=HTTPException(status_code=400, detail="Invalid reset token: token has expired")
    )

    app.dependency_overrides[get_tenant_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/password-reset/confirm",
                json={"token": "expired.tok", "new_password": "GoodPassword123!"},
                headers=_SLUG_HEADER,
            )
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/iam/tenant_auth/test_tenant_auth_api.py -v -k "reset"
```

Expected: 404 — routes do not exist yet

- [ ] **Step 3: Add reset routes to `app/modules/iam/tenant_auth/api.py`**

Update the import from `tenant_auth.schemas` to include the reset schemas:

```python
from app.modules.iam.tenant_auth.schemas import (
    TenantLoginRequest,
    TenantPasswordResetConfirmBody,
    TenantPasswordResetRequestBody,
    TenantRefreshRequest,
    TenantTokenResponse,
    TenantUserOut,
)
```

Then append these two routes after the `tenant_me` route:

```python
@router.post("/password-reset/request", status_code=204)
async def tenant_reset_request(
    body: TenantPasswordResetRequestBody,
    svc: TenantAuth,
) -> Response:
    """Request a password reset link for a tenant user.

    Always returns 204 — response is identical whether or not the email
    exists, preventing user enumeration.
    """
    await svc.reset_request(body.email)
    return Response(status_code=204)


@router.post("/password-reset/confirm", status_code=204)
async def tenant_reset_confirm(
    body: TenantPasswordResetConfirmBody,
    svc: TenantAuth,
) -> Response:
    """Confirm a tenant user password reset using the token from the request email."""
    await svc.reset_confirm(token=body.token, new_password=body.new_password)
    return Response(status_code=204)
```

- [ ] **Step 4: Run all tenant auth tests to confirm pass**

```bash
pytest tests/modules/iam/tenant_auth/ -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/modules/iam/tenant_auth/api.py \
        tests/modules/iam/tenant_auth/test_tenant_auth_api.py
git commit -m "feat(iam): POST /auth/password-reset/request and /confirm"
```

---

## Verification Criteria

Before marking this plan complete, run the following in order:

```bash
# 1. Linting — zero errors
ruff check app/modules/iam/reset_tokens.py \
           app/modules/iam/platform_auth/ \
           app/modules/iam/tenant_auth/

# 2. Type checking — zero errors
mypy app/modules/iam/reset_tokens.py \
     app/modules/iam/platform_auth/ \
     app/modules/iam/tenant_auth/ --strict

# 3. Reset token unit tests (fast — no DB, no async)
pytest tests/modules/iam/test_reset_tokens.py -v

# 4. Platform auth full suite
pytest tests/modules/iam/platform_auth/ -v

# 5. Tenant auth full suite
pytest tests/modules/iam/tenant_auth/ -v

# 6. Full suite — no regressions
pytest tests/ -v
```

All commands must exit cleanly before this plan is considered complete.

---

## What is NOT in this plan

- **Email delivery** — the notifier is a structlog warning. Plugging in a real email sender (SMTP, SendGrid, etc.) is an infrastructure task outside the IAM v1 scope. The call site is clearly marked with a comment.
- **Rate limiting on reset request** — not in v1. The endpoint returns 204 for unknown emails so brute-force enumeration is already mitigated. Rate limiting can be added at the API gateway layer.
- **Audit events** (`platform_auth.password_reset_requested`, `platform_auth.password_reset_confirmed`, tenant equivalents) — added in Plan 11. The insertion points are marked with comments.
- **`last_login_at` update on login** — if Plans 05 and 06 did not set `user.last_login_at = datetime.now(UTC)` inside `login()`, add it alongside the `needs_rehash` block. Plan 08 does not add this — it belongs in the login flow.
