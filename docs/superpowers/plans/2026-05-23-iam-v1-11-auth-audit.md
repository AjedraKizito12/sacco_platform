# IAM v1-11: Auth Audit Events Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire audit records into every auth operation — 16 event types across platform and tenant services — so every authentication action is permanently logged to `audit_log`.

**Architecture:** A thin helper module (`app/modules/iam/auth_audit.py`) wraps `PlatformAuditService` and `TenantAuditService` with auth-specific defaults. Both auth services import the helper and call it at each success/failure point. The helpers do `session.add()` inside the existing transaction — no extra commits required. Tests for the helper use the real DB (write + commit + query + cleanup). Tests for the service-level wiring patch the helper and assert it was called with the correct arguments.

**Tech Stack:** SQLAlchemy 2.0 async, `app.core.audit.service` (`PlatformAuditService`, `TenantAuditService`), structlog, pytest-anyio, `unittest.mock.AsyncMock`

---

## Required Reading (complete before starting any task)

1. `CLAUDE.md` — architectural rule 8: every sensitive operation writes to `audit_log`
2. `app/core/audit/service.py` — `PlatformAuditService.record()` and `TenantAuditService.record()` signatures
3. `app/core/audit/models.py` — `PlatformAuditLog` and `TenantAuditLog` column layout
4. `tests/core/audit/test_audit_service.py` — DB test pattern: write → commit → query → cleanup
5. `app/modules/iam/platform_auth/service.py` — current state after Plans 05, 07, 08, 10; contains all `# Plan 11 adds:` stubs
6. `app/modules/iam/tenant_auth/service.py` — current state after Plans 06, 07, 08, 10; same stubs
7. `docs/superpowers/plans/2026-05-23-iam-v1-10-lockout.md` — Task 3 and Task 4: the full `login()` method body that replaced Plan 05/06's versions; Plan 11 adds audit calls to this body

---

## Prerequisite: Locate all `# Plan 11 adds:` stubs

Before writing any code, grep for every stub so you know exactly what you're replacing:

```bash
grep -rn "Plan 11 adds" app/modules/iam/
```

You should see 16 lines (8 per service file). If you see fewer, earlier plans may not be fully merged — resolve that before continuing.

---

## File Map

```
CREATE app/modules/iam/auth_audit.py                              — platform + tenant audit event helpers
CREATE tests/modules/iam/test_auth_audit.py                       — DB-level helper unit tests
MODIFY app/modules/iam/platform_auth/service.py                   — replace 8 stubs; add login_failed + login_locked calls
MODIFY app/modules/iam/tenant_auth/service.py                     — replace 8 stubs; add login_failed + login_locked calls
MODIFY tests/modules/iam/platform_auth/test_platform_auth_service.py — audit assertion tests
MODIFY tests/modules/iam/tenant_auth/test_tenant_auth_service.py  — audit assertion tests
```

---

### Task 1: `auth_audit.py` helper module

**Files:**
- Create: `app/modules/iam/auth_audit.py`
- Create: `tests/modules/iam/test_auth_audit.py`

- [ ] **Step 1: Write the failing DB tests**

```python
# tests/modules/iam/test_auth_audit.py
"""Integration tests for write_platform_auth_event and write_tenant_auth_event.

Each test commits to the real DB then queries and cleans up. This follows the
pattern in tests/core/audit/test_audit_service.py.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.audit.models import PlatformAuditLog, TenantAuditLog

TEST_TENANT_SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.anyio
async def test_write_platform_auth_event_writes_row(test_engine: AsyncEngine) -> None:
    from app.modules.iam.auth_audit import write_platform_auth_event

    factory = _factory(test_engine)
    user_id = uuid.uuid4()

    async with factory() as session:
        await session.execute(text("SET search_path TO platform"))
        await write_platform_auth_event(
            db=session,
            operation="login_success",
            actor_id=user_id,
            actor_label="user@example.com",
            after_state={"session_id": str(uuid.uuid4())},
        )
        await session.commit()

    async with factory() as session:
        await session.execute(text("SET search_path TO platform"))
        rows = (await session.execute(select(PlatformAuditLog))).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.operation == "login_success"
        assert row.actor_id == user_id
        assert row.actor_type == "platform_user"
        assert row.actor_label == "user@example.com"
        assert row.table_name == "platform_sessions"

    async with factory() as session:
        await session.execute(text("SET search_path TO platform"))
        await session.execute(delete(PlatformAuditLog))
        await session.commit()


@pytest.mark.anyio
async def test_write_platform_auth_event_anonymous_uses_nil_uuid(test_engine: AsyncEngine) -> None:
    from app.modules.iam.auth_audit import write_platform_auth_event

    factory = _factory(test_engine)

    async with factory() as session:
        await session.execute(text("SET search_path TO platform"))
        await write_platform_auth_event(
            db=session,
            operation="login_failed",
            actor_id=None,
            actor_label=None,
            after_state={"email": "unknown@example.com", "reason": "user_not_found"},
        )
        await session.commit()

    async with factory() as session:
        await session.execute(text("SET search_path TO platform"))
        rows = (await session.execute(select(PlatformAuditLog))).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.actor_type == "anonymous"
        assert row.actor_id is None
        assert row.record_id == uuid.UUID(int=0)

    async with factory() as session:
        await session.execute(text("SET search_path TO platform"))
        await session.execute(delete(PlatformAuditLog))
        await session.commit()


@pytest.mark.anyio
async def test_write_tenant_auth_event_writes_row(test_engine: AsyncEngine) -> None:
    from app.modules.iam.auth_audit import write_tenant_auth_event

    factory = _factory(test_engine)
    user_id = uuid.uuid4()

    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        await write_tenant_auth_event(
            db=session,
            operation="login_success",
            actor_id=user_id,
            actor_label="member@sacco.org",
            tenant_slug="test-sacco",
            after_state={"session_id": str(uuid.uuid4())},
        )
        await session.commit()

    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        rows = (await session.execute(select(TenantAuditLog))).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.operation == "login_success"
        assert row.actor_id == user_id
        assert row.actor_type == "tenant_user"
        assert row.table_name == "tenant_sessions"
        assert row.after_state["tenant"] == "test-sacco"

    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        await session.execute(delete(TenantAuditLog))
        await session.commit()


@pytest.mark.anyio
async def test_write_tenant_auth_event_user_table_for_reset(test_engine: AsyncEngine) -> None:
    from app.modules.iam.auth_audit import write_tenant_auth_event

    factory = _factory(test_engine)
    user_id = uuid.uuid4()

    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        await write_tenant_auth_event(
            db=session,
            operation="password_reset_confirmed",
            actor_id=user_id,
            actor_label="member@sacco.org",
            tenant_slug="test-sacco",
            table_name="tenant_users",
        )
        await session.commit()

    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        rows = (await session.execute(select(TenantAuditLog))).scalars().all()
        assert len(rows) == 1
        assert rows[0].table_name == "tenant_users"
        assert rows[0].operation == "password_reset_confirmed"

    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        await session.execute(delete(TenantAuditLog))
        await session.commit()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/modules/iam/test_auth_audit.py -v
```

Expected: `ImportError: cannot import name 'write_platform_auth_event' from 'app.modules.iam.auth_audit'` (module does not exist yet)

- [ ] **Step 3: Create `app/modules/iam/auth_audit.py`**

```python
"""Auth audit event helpers.

Thin wrappers around PlatformAuditService and TenantAuditService that
standardise table_name, actor_type, and record_id for each auth operation.

Both helpers are fire-and-forget: they call session.add() which is committed
as part of the surrounding transaction. No extra commit calls are needed.

table_name conventions:
  "platform_sessions" — session-scope events (login, refresh, logout, me)
  "platform_users"    — user-scope events (password_reset_requested/confirmed)
  "tenant_sessions"   — same as above for tenant side
  "tenant_users"      — same as above for tenant side
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.service import PlatformAuditService, TenantAuditService

_NIL_UUID = uuid.UUID(int=0)  # record_id when no user is known (anonymous events)

_SESSION_OPERATIONS = frozenset({
    "login_success",
    "login_failed",
    "login_locked",
    "refresh",
    "logout",
    "me",
})


def _platform_table(operation: str, override: str | None) -> str:
    if override:
        return override
    return "platform_sessions" if operation in _SESSION_OPERATIONS else "platform_users"


def _tenant_table(operation: str, override: str | None) -> str:
    if override:
        return override
    return "tenant_sessions" if operation in _SESSION_OPERATIONS else "tenant_users"


async def write_platform_auth_event(
    *,
    db: AsyncSession,
    operation: str,
    actor_id: uuid.UUID | None,
    actor_label: str | None = None,
    after_state: dict[str, Any] | None = None,
    table_name: str | None = None,
) -> None:
    """Write a single platform auth audit row to platform.audit_log.

    Args:
        db:           Platform DB session (search_path=platform already set by middleware).
        operation:    Auth event type, e.g. "login_success", "login_failed".
        actor_id:     PlatformUser.id. Pass None for anonymous events (user not found).
        actor_label:  Email address of the actor (for human-readable audit trail).
        after_state:  Optional dict of event context (session_id, ip_address, etc.).
        table_name:   Override the auto-detected table name.
    """
    svc = PlatformAuditService(db)
    await svc.record(
        table_name=_platform_table(operation, table_name),
        record_id=actor_id if actor_id is not None else _NIL_UUID,
        operation=operation,
        actor_type="platform_user" if actor_id is not None else "anonymous",
        actor_id=actor_id,
        actor_label=actor_label,
        after_state=after_state,
    )


async def write_tenant_auth_event(
    *,
    db: AsyncSession,
    operation: str,
    actor_id: uuid.UUID | None,
    actor_label: str | None = None,
    tenant_slug: str | None = None,
    after_state: dict[str, Any] | None = None,
    table_name: str | None = None,
) -> None:
    """Write a single tenant auth audit row to the tenant audit_log.

    Args:
        db:           Tenant DB session (search_path set by middleware).
        operation:    Auth event type, e.g. "login_success", "tenant_auth.me".
        actor_id:     TenantUser.id. Pass None for anonymous events.
        actor_label:  Email address of the actor.
        tenant_slug:  Tenant slug — appended to after_state for context.
        after_state:  Optional dict of event context.
        table_name:   Override the auto-detected table name.
    """
    svc = TenantAuditService(db)
    state: dict[str, Any] = dict(after_state or {})
    if tenant_slug:
        state["tenant"] = tenant_slug
    await svc.record(
        table_name=_tenant_table(operation, table_name),
        record_id=actor_id if actor_id is not None else _NIL_UUID,
        operation=operation,
        actor_type="tenant_user" if actor_id is not None else "anonymous",
        actor_id=actor_id,
        actor_label=actor_label,
        after_state=state if state else None,
    )
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
pytest tests/modules/iam/test_auth_audit.py -v
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/modules/iam/auth_audit.py tests/modules/iam/test_auth_audit.py
git commit -m "feat(iam): auth_audit helpers — write_platform_auth_event, write_tenant_auth_event"
```

---

### Task 2: Wire audit into `PlatformAuthService`

**Files:**
- Modify: `app/modules/iam/platform_auth/service.py`
- Modify: `tests/modules/iam/platform_auth/test_platform_auth_service.py`

**Events wired:**
`login_success`, `login_failed`, `login_locked`, `refresh`, `logout`, `me`, `password_reset_requested`, `password_reset_confirmed`

- [ ] **Step 1: Write the failing tests**

Append to `tests/modules/iam/platform_auth/test_platform_auth_service.py`:

```python
# ── audit event assertions ────────────────────────────────────────────────────
# These tests patch write_platform_auth_event and assert it is called with the
# correct operation keyword argument. The DB-level write is tested in
# tests/modules/iam/test_auth_audit.py.

from unittest.mock import patch


@pytest.mark.anyio
async def test_login_success_fires_audit_event(
    platform_session, mock_key_service, active_user
):
    with patch(
        "app.modules.iam.platform_auth.service.write_platform_auth_event"
    ) as mock_audit:
        mock_audit.return_value = _coro(None)
        svc = _make_service(platform_session, mock_key_service)
        await svc.login(
            email=active_user.email,
            password=_PASSWORD,
            user_agent="pytest",
            ip_address="127.0.0.1",
        )
    calls = [c.kwargs["operation"] for c in mock_audit.call_args_list]
    assert "login_success" in calls


@pytest.mark.anyio
async def test_login_failed_fires_audit_event_on_wrong_password(
    platform_session, mock_key_service, active_user
):
    with patch(
        "app.modules.iam.platform_auth.service.write_platform_auth_event"
    ) as mock_audit:
        mock_audit.return_value = _coro(None)
        svc = _make_service(platform_session, mock_key_service)
        with pytest.raises(Exception):  # HTTPException 401
            await svc.login(
                email=active_user.email,
                password="wrongpassword",
                user_agent="pytest",
                ip_address="127.0.0.1",
            )
    calls = [c.kwargs["operation"] for c in mock_audit.call_args_list]
    assert "login_failed" in calls


@pytest.mark.anyio
async def test_login_failed_fires_audit_event_on_unknown_email(
    platform_session, mock_key_service
):
    with patch(
        "app.modules.iam.platform_auth.service.write_platform_auth_event"
    ) as mock_audit:
        mock_audit.return_value = _coro(None)
        svc = _make_service(platform_session, mock_key_service)
        with pytest.raises(Exception):  # HTTPException 401
            await svc.login(
                email="nosuchuser@example.com",
                password="anything",
                user_agent="pytest",
                ip_address="127.0.0.1",
            )
    calls = [c.kwargs["operation"] for c in mock_audit.call_args_list]
    assert "login_failed" in calls


@pytest.mark.anyio
async def test_refresh_fires_audit_event(
    platform_session, mock_key_service, active_user
):
    svc = _make_service(platform_session, mock_key_service)
    token_resp = await svc.login(
        email=active_user.email,
        password=_PASSWORD,
        user_agent="pytest",
        ip_address="127.0.0.1",
    )
    with patch(
        "app.modules.iam.platform_auth.service.write_platform_auth_event"
    ) as mock_audit:
        mock_audit.return_value = _coro(None)
        await svc.refresh(token_resp.refresh_token)
    calls = [c.kwargs["operation"] for c in mock_audit.call_args_list]
    assert "refresh" in calls


@pytest.mark.anyio
async def test_logout_fires_audit_event(
    platform_session, mock_key_service, active_user
):
    svc = _make_service(platform_session, mock_key_service)
    token_resp = await svc.login(
        email=active_user.email,
        password=_PASSWORD,
        user_agent="pytest",
        ip_address="127.0.0.1",
    )
    with patch(
        "app.modules.iam.platform_auth.service.write_platform_auth_event"
    ) as mock_audit:
        mock_audit.return_value = _coro(None)
        await svc.logout(token_resp.access_token)
    calls = [c.kwargs["operation"] for c in mock_audit.call_args_list]
    assert "logout" in calls


@pytest.mark.anyio
async def test_me_fires_audit_event(platform_session, mock_key_service, active_user):
    svc = _make_service(platform_session, mock_key_service)
    token_resp = await svc.login(
        email=active_user.email,
        password=_PASSWORD,
        user_agent="pytest",
        ip_address="127.0.0.1",
    )
    with patch(
        "app.modules.iam.platform_auth.service.write_platform_auth_event"
    ) as mock_audit:
        mock_audit.return_value = _coro(None)
        await svc.me(token_resp.access_token)
    calls = [c.kwargs["operation"] for c in mock_audit.call_args_list]
    assert "me" in calls


@pytest.mark.anyio
async def test_reset_request_fires_audit_event(
    platform_session, mock_key_service, active_user
):
    svc = _make_service(platform_session, mock_key_service)
    with patch(
        "app.modules.iam.platform_auth.service.write_platform_auth_event"
    ) as mock_audit:
        mock_audit.return_value = _coro(None)
        await svc.reset_request(email=active_user.email)
    calls = [c.kwargs["operation"] for c in mock_audit.call_args_list]
    assert "password_reset_requested" in calls


@pytest.mark.anyio
async def test_reset_request_no_audit_for_unknown_email(
    platform_session, mock_key_service
):
    """reset_request must NOT reveal whether the email exists — no audit row
    should be written when the user is not found (prevents enumeration via
    timing side-channels in audit storage)."""
    svc = _make_service(platform_session, mock_key_service)
    with patch(
        "app.modules.iam.platform_auth.service.write_platform_auth_event"
    ) as mock_audit:
        mock_audit.return_value = _coro(None)
        await svc.reset_request(email="nosuchuser@example.com")
    mock_audit.assert_not_called()


@pytest.mark.anyio
async def test_reset_confirm_fires_audit_event(
    platform_session, mock_key_service, active_user
):
    from app.modules.iam.reset_tokens import make_reset_token
    from app.core.config import get_settings

    settings = get_settings()
    token, _ = make_reset_token(str(active_user.id), settings.app_secret_key)
    svc = _make_service(platform_session, mock_key_service)
    with patch(
        "app.modules.iam.platform_auth.service.write_platform_auth_event"
    ) as mock_audit:
        mock_audit.return_value = _coro(None)
        await svc.reset_confirm(token=token, new_password="NewSecurePass99!")
    calls = [c.kwargs["operation"] for c in mock_audit.call_args_list]
    assert "password_reset_confirmed" in calls
```

Also add this helper at the top of the test file (after existing imports) so that `mock_audit.return_value = _coro(None)` works:

```python
import asyncio

def _coro(val):
    """Return a coroutine that yields val — used to mock async functions."""
    async def _inner():
        return val
    return _inner()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/modules/iam/platform_auth/test_platform_auth_service.py -v -k "audit"
```

Expected: tests FAIL (stubs are comments, not real calls, so patch finds nothing to intercept)

- [ ] **Step 3: Add import and wire audit calls in `app/modules/iam/platform_auth/service.py`**

**3a — Add the import** (alongside existing imports at the top of the file):

```python
from app.modules.iam.auth_audit import write_platform_auth_event
```

**3b — Update `login()`** (this replaces the full method body delivered by Plan 10 Task 3). The only changes are replacing `# Plan 11 adds: audit("platform_auth.login_success", ...)` with a real call, and adding `write_platform_auth_event` calls before each `raise HTTPException`:

```python
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
            HTTPException 423: account locked due to too many failed attempts.
        """
        settings = get_settings()

        # 1. Look up user.
        result = await self._db.execute(
            select(PlatformUser).where(PlatformUser.email == email)
        )
        user = result.scalar_one_or_none()

        if user is None or not user.is_active:
            await record_attempt(email, self._redis)
            await write_platform_auth_event(
                db=self._db,
                operation="login_failed",
                actor_id=None,
                actor_label=email,
                after_state={"email": email, "reason": "user_not_found_or_inactive"},
            )
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # 2. Check lockout — only for users that actually exist.
        locked, retry_after = await is_locked(email, self._redis)
        if locked:
            await write_platform_auth_event(
                db=self._db,
                operation="login_locked",
                actor_id=user.id,
                actor_label=user.email,
                after_state={"retry_after": retry_after},
            )
            raise HTTPException(
                status_code=423,
                detail="Account locked due to too many failed attempts",
                headers={"Retry-After": str(retry_after)},
            )

        # 3. Verify password.
        if not user.hashed_password or not verify_password(password, user.hashed_password):
            await record_attempt(email, self._redis)
            await write_platform_auth_event(
                db=self._db,
                operation="login_failed",
                actor_id=user.id,
                actor_label=user.email,
                after_state={"reason": "wrong_password"},
            )
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # 4. Successful auth — clear lockout state.
        await reset_lockout(email, self._redis)

        # 5. Transparent rehash.
        if needs_rehash(user.hashed_password):
            user.hashed_password = hash_password(password)

        # 6. Fetch active signing key.
        kid, private_key, algorithm = await self._key_service.get_active_signing_key(
            _AUDIENCE
        )

        # 7. Pre-generate JTI.
        jti = str(uuid.uuid4())

        # 8. Create session row.
        session_row = await self._session_svc.create(
            user_id=user.id,
            jti=jti,
            user_agent=user_agent,
            ip_address=ip_address,
            refresh_ttl_seconds=settings.jwt_refresh_ttl_platform_seconds,
        )

        # 9. Issue tokens.
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

        await write_platform_auth_event(
            db=self._db,
            operation="login_success",
            actor_id=user.id,
            actor_label=user.email,
            after_state={
                "session_id": str(session_row.id),
                "user_agent": user_agent,
                "ip_address": ip_address,
            },
        )
        _log.info("platform_auth.login_success", user_id=str(user.id))
        return PlatformTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=access_ttl,
        )
```

**3c — Update `refresh()`**: Find the line `# Plan 11 adds: audit("platform_auth.refresh", session_id=session_id_str)` and replace it with:

```python
        await write_platform_auth_event(
            db=self._db,
            operation="refresh",
            actor_id=uuid.UUID(claims["sub"]),
            after_state={"session_id": session_id_str},
        )
```

**3d — Update `logout()`**: Find the line `# Plan 11 adds: audit("platform_auth.logout", session_id=session_id_str)` and replace it with:

```python
        await write_platform_auth_event(
            db=self._db,
            operation="logout",
            actor_id=uuid.UUID(claims["sub"]) if "sub" in claims else None,
            after_state={"session_id": session_id_str},
        )
```

**3e — Update `me()`**: Find the line `# Plan 11 adds: audit("platform_auth.me", user_id=str(user.id))` and replace it with:

```python
        await write_platform_auth_event(
            db=self._db,
            operation="me",
            actor_id=user.id,
            actor_label=user.email,
            after_state={"session_id": session_id_str},
        )
```

**3f — Update `reset_request()`**: Find the line `# Plan 11 adds: audit("platform_auth.password_reset_requested", user_id=str(user.id))` and replace it with:

```python
        await write_platform_auth_event(
            db=self._db,
            operation="password_reset_requested",
            actor_id=user.id,
            actor_label=user.email,
            table_name="platform_users",
        )
```

**3g — Update `reset_confirm()`**: Find the line `# Plan 11 adds: audit("platform_auth.password_reset_confirmed", user_id=str(user.id))` and replace it with:

```python
        await write_platform_auth_event(
            db=self._db,
            operation="password_reset_confirmed",
            actor_id=user.id,
            actor_label=user.email,
            table_name="platform_users",
        )
```

- [ ] **Step 4: Verify no stubs remain**

```bash
grep -n "Plan 11 adds" app/modules/iam/platform_auth/service.py
```

Expected: no output (all 8 stubs replaced)

- [ ] **Step 5: Run new audit tests**

```bash
pytest tests/modules/iam/platform_auth/test_platform_auth_service.py -v -k "audit"
```

Expected: 9 tests PASS

- [ ] **Step 6: Run full platform auth suite to confirm no regressions**

```bash
pytest tests/modules/iam/platform_auth/ -v
```

Expected: all tests PASS. Total time ~20–30 s (argon2id × many calls).

- [ ] **Step 7: Commit**

```bash
git add app/modules/iam/platform_auth/service.py \
        tests/modules/iam/platform_auth/test_platform_auth_service.py
git commit -m "feat(iam): wire audit events into PlatformAuthService (8 event types)"
```

---

### Task 3: Wire audit into `TenantAuthService`

**Files:**
- Modify: `app/modules/iam/tenant_auth/service.py`
- Modify: `tests/modules/iam/tenant_auth/test_tenant_auth_service.py`

**Events wired:**
`login_success`, `login_failed`, `login_locked`, `refresh`, `logout`, `me`, `password_reset_requested`, `password_reset_confirmed`

- [ ] **Step 1: Write the failing tests**

Append to `tests/modules/iam/tenant_auth/test_tenant_auth_service.py`:

```python
# ── audit event assertions ────────────────────────────────────────────────────

import asyncio
from unittest.mock import patch


def _coro(val):
    async def _inner():
        return val
    return _inner()


@pytest.mark.anyio
async def test_tenant_login_success_fires_audit_event(
    tenant_session, mock_key_service, active_tenant_user
):
    svc = _make_service(tenant_session, mock_key_service, slug="test-sacco")
    with patch(
        "app.modules.iam.tenant_auth.service.write_tenant_auth_event"
    ) as mock_audit:
        mock_audit.return_value = _coro(None)
        await svc.login(
            email=active_tenant_user.email,
            password=_PASSWORD,
            user_agent="pytest",
            ip_address="127.0.0.1",
        )
    calls = [c.kwargs["operation"] for c in mock_audit.call_args_list]
    assert "login_success" in calls


@pytest.mark.anyio
async def test_tenant_login_failed_fires_audit_event_on_wrong_password(
    tenant_session, mock_key_service, active_tenant_user
):
    svc = _make_service(tenant_session, mock_key_service, slug="test-sacco")
    with patch(
        "app.modules.iam.tenant_auth.service.write_tenant_auth_event"
    ) as mock_audit:
        mock_audit.return_value = _coro(None)
        with pytest.raises(Exception):
            await svc.login(
                email=active_tenant_user.email,
                password="wrongpassword",
                user_agent="pytest",
                ip_address="127.0.0.1",
            )
    calls = [c.kwargs["operation"] for c in mock_audit.call_args_list]
    assert "login_failed" in calls


@pytest.mark.anyio
async def test_tenant_login_failed_fires_audit_event_on_unknown_email(
    tenant_session, mock_key_service
):
    svc = _make_service(tenant_session, mock_key_service, slug="test-sacco")
    with patch(
        "app.modules.iam.tenant_auth.service.write_tenant_auth_event"
    ) as mock_audit:
        mock_audit.return_value = _coro(None)
        with pytest.raises(Exception):
            await svc.login(
                email="nosuchuser@example.com",
                password="anything",
                user_agent="pytest",
                ip_address="127.0.0.1",
            )
    calls = [c.kwargs["operation"] for c in mock_audit.call_args_list]
    assert "login_failed" in calls


@pytest.mark.anyio
async def test_tenant_refresh_fires_audit_event(
    tenant_session, mock_key_service, active_tenant_user
):
    svc = _make_service(tenant_session, mock_key_service, slug="test-sacco")
    token_resp = await svc.login(
        email=active_tenant_user.email,
        password=_PASSWORD,
        user_agent="pytest",
        ip_address="127.0.0.1",
    )
    with patch(
        "app.modules.iam.tenant_auth.service.write_tenant_auth_event"
    ) as mock_audit:
        mock_audit.return_value = _coro(None)
        await svc.refresh(token_resp.refresh_token)
    calls = [c.kwargs["operation"] for c in mock_audit.call_args_list]
    assert "refresh" in calls


@pytest.mark.anyio
async def test_tenant_logout_fires_audit_event(
    tenant_session, mock_key_service, active_tenant_user
):
    svc = _make_service(tenant_session, mock_key_service, slug="test-sacco")
    token_resp = await svc.login(
        email=active_tenant_user.email,
        password=_PASSWORD,
        user_agent="pytest",
        ip_address="127.0.0.1",
    )
    with patch(
        "app.modules.iam.tenant_auth.service.write_tenant_auth_event"
    ) as mock_audit:
        mock_audit.return_value = _coro(None)
        await svc.logout(token_resp.access_token)
    calls = [c.kwargs["operation"] for c in mock_audit.call_args_list]
    assert "logout" in calls


@pytest.mark.anyio
async def test_tenant_me_fires_audit_event(
    tenant_session, mock_key_service, active_tenant_user
):
    svc = _make_service(tenant_session, mock_key_service, slug="test-sacco")
    token_resp = await svc.login(
        email=active_tenant_user.email,
        password=_PASSWORD,
        user_agent="pytest",
        ip_address="127.0.0.1",
    )
    with patch(
        "app.modules.iam.tenant_auth.service.write_tenant_auth_event"
    ) as mock_audit:
        mock_audit.return_value = _coro(None)
        await svc.me(token_resp.access_token)
    calls = [c.kwargs["operation"] for c in mock_audit.call_args_list]
    assert "me" in calls


@pytest.mark.anyio
async def test_tenant_reset_request_fires_audit_event(
    tenant_session, mock_key_service, active_tenant_user
):
    svc = _make_service(tenant_session, mock_key_service, slug="test-sacco")
    with patch(
        "app.modules.iam.tenant_auth.service.write_tenant_auth_event"
    ) as mock_audit:
        mock_audit.return_value = _coro(None)
        await svc.reset_request(email=active_tenant_user.email)
    calls = [c.kwargs["operation"] for c in mock_audit.call_args_list]
    assert "password_reset_requested" in calls


@pytest.mark.anyio
async def test_tenant_reset_request_no_audit_for_unknown_email(
    tenant_session, mock_key_service
):
    svc = _make_service(tenant_session, mock_key_service, slug="test-sacco")
    with patch(
        "app.modules.iam.tenant_auth.service.write_tenant_auth_event"
    ) as mock_audit:
        mock_audit.return_value = _coro(None)
        await svc.reset_request(email="nosuchuser@example.com")
    mock_audit.assert_not_called()


@pytest.mark.anyio
async def test_tenant_reset_confirm_fires_audit_event(
    tenant_session, mock_key_service, active_tenant_user
):
    from app.modules.iam.reset_tokens import make_reset_token
    from app.core.config import get_settings

    settings = get_settings()
    token, _ = make_reset_token(str(active_tenant_user.id), settings.app_secret_key)
    svc = _make_service(tenant_session, mock_key_service, slug="test-sacco")
    with patch(
        "app.modules.iam.tenant_auth.service.write_tenant_auth_event"
    ) as mock_audit:
        mock_audit.return_value = _coro(None)
        await svc.reset_confirm(token=token, new_password="NewSecurePass99!")
    calls = [c.kwargs["operation"] for c in mock_audit.call_args_list]
    assert "password_reset_confirmed" in calls
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/modules/iam/tenant_auth/test_tenant_auth_service.py -v -k "audit"
```

Expected: tests FAIL (stubs are comments, patch finds nothing)

- [ ] **Step 3: Add import and wire audit calls in `app/modules/iam/tenant_auth/service.py`**

**3a — Add the import** (alongside existing imports):

```python
from app.modules.iam.auth_audit import write_tenant_auth_event
```

**3b — Update `login()`** (replaces Plan 10 Task 4 version):

```python
    async def login(
        self,
        email: str,
        password: str,
        user_agent: str | None,
        ip_address: str | None,
    ) -> TenantTokenResponse:
        """Full login flow for tenant users.

        Raises:
            HTTPException 401: unknown email, wrong password, or inactive user.
            HTTPException 423: account locked due to too many failed attempts.
        """
        settings = get_settings()

        # 1. Look up user.
        result = await self._db.execute(
            select(TenantUser).where(TenantUser.email == email)
        )
        user = result.scalar_one_or_none()

        if user is None or not user.is_active:
            await record_attempt(email, self._redis)
            await write_tenant_auth_event(
                db=self._db,
                operation="login_failed",
                actor_id=None,
                actor_label=email,
                tenant_slug=self._slug,
                after_state={"email": email, "reason": "user_not_found_or_inactive"},
            )
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # 2. Check lockout.
        locked, retry_after = await is_locked(email, self._redis)
        if locked:
            await write_tenant_auth_event(
                db=self._db,
                operation="login_locked",
                actor_id=user.id,
                actor_label=user.email,
                tenant_slug=self._slug,
                after_state={"retry_after": retry_after},
            )
            raise HTTPException(
                status_code=423,
                detail="Account locked due to too many failed attempts",
                headers={"Retry-After": str(retry_after)},
            )

        # 3. Verify password.
        if not user.hashed_password or not verify_password(password, user.hashed_password):
            await record_attempt(email, self._redis)
            await write_tenant_auth_event(
                db=self._db,
                operation="login_failed",
                actor_id=user.id,
                actor_label=user.email,
                tenant_slug=self._slug,
                after_state={"reason": "wrong_password"},
            )
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # 4. Successful auth — clear lockout state.
        await reset_lockout(email, self._redis)

        # 5. Transparent rehash.
        if needs_rehash(user.hashed_password):
            user.hashed_password = hash_password(password)

        # 6. Fetch active signing key (DB column = "tenant").
        kid, private_key, algorithm = await self._key_service.get_active_signing_key(
            _KEY_AUDIENCE
        )

        # 7. Pre-generate JTI.
        jti = str(uuid.uuid4())

        # 8. Create session row.
        session_row = await self._session_svc.create(
            user_id=user.id,
            jti=jti,
            user_agent=user_agent,
            ip_address=ip_address,
            refresh_ttl_seconds=settings.jwt_refresh_ttl_tenant_seconds,
        )

        # 9. Issue tokens. JWT aud = "tenant:<slug>".
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

        await write_tenant_auth_event(
            db=self._db,
            operation="login_success",
            actor_id=user.id,
            actor_label=user.email,
            tenant_slug=self._slug,
            after_state={
                "session_id": str(session_row.id),
                "user_agent": user_agent,
                "ip_address": ip_address,
            },
        )
        _log.info("tenant_auth.login_success", user_id=str(user.id), tenant=self._slug)
        return TenantTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=access_ttl,
        )
```

**3c — Update `refresh()`**: Find `# Plan 11 adds: audit("tenant_auth.refresh", ...)` and replace with:

```python
        await write_tenant_auth_event(
            db=self._db,
            operation="refresh",
            actor_id=uuid.UUID(claims["sub"]),
            tenant_slug=self._slug,
            after_state={"session_id": session_id_str},
        )
```

**3d — Update `logout()`**: Find `# Plan 11 adds: audit("tenant_auth.logout", ...)` and replace with:

```python
        await write_tenant_auth_event(
            db=self._db,
            operation="logout",
            actor_id=uuid.UUID(claims["sub"]) if "sub" in claims else None,
            tenant_slug=self._slug,
            after_state={"session_id": session_id_str},
        )
```

**3e — Update `me()`**: Find `# Plan 11 adds: audit("tenant_auth.me", user_id=str(user.id))` and replace with:

```python
        await write_tenant_auth_event(
            db=self._db,
            operation="me",
            actor_id=user.id,
            actor_label=user.email,
            tenant_slug=self._slug,
            after_state={"session_id": session_id_str},
        )
```

**3f — Update `reset_request()`**: Find `# Plan 11 adds: audit("tenant_auth.password_reset_requested", user_id=str(user.id))` and replace with:

```python
        await write_tenant_auth_event(
            db=self._db,
            operation="password_reset_requested",
            actor_id=user.id,
            actor_label=user.email,
            tenant_slug=self._slug,
            table_name="tenant_users",
        )
```

**3g — Update `reset_confirm()`**: Find `# Plan 11 adds: audit("tenant_auth.password_reset_confirmed", user_id=str(user.id))` and replace with:

```python
        await write_tenant_auth_event(
            db=self._db,
            operation="password_reset_confirmed",
            actor_id=user.id,
            actor_label=user.email,
            tenant_slug=self._slug,
            table_name="tenant_users",
        )
```

- [ ] **Step 4: Verify no stubs remain**

```bash
grep -n "Plan 11 adds" app/modules/iam/tenant_auth/service.py
```

Expected: no output

- [ ] **Step 5: Run new audit tests**

```bash
pytest tests/modules/iam/tenant_auth/test_tenant_auth_service.py -v -k "audit"
```

Expected: 9 tests PASS

- [ ] **Step 6: Run full tenant auth suite**

```bash
pytest tests/modules/iam/tenant_auth/ -v
```

Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add app/modules/iam/tenant_auth/service.py \
        tests/modules/iam/tenant_auth/test_tenant_auth_service.py
git commit -m "feat(iam): wire audit events into TenantAuthService (8 event types)"
```

---

## Final Verification

- [ ] **No remaining stubs anywhere in the IAM module**

```bash
grep -rn "Plan 11 adds" app/modules/iam/
```

Expected: no output

- [ ] **Linter and type checker**

```bash
ruff check app/modules/iam/
mypy app/modules/iam/ --strict
```

Expected: zero errors

- [ ] **Full IAM test suite**

```bash
pytest tests/modules/iam/ -v
```

Expected: all tests PASS

- [ ] **No regressions outside IAM**

```bash
pytest tests/ -v --ignore=tests/modules/iam/
```

Expected: all tests PASS

---

## What Is NOT in This Plan

- **Audit on `KeyService.rotate_signing_keys_if_due` and `advance_key_lifecycle`** — the index entry `iam.key_rotated` and `iam.key_lifecycle_advanced` are delivered in Plan 01 (Celery beat tasks). If those are not yet present, they are a Plan 01 gap, not scope for Plan 11.
- **Audit on failed token decode attempts** (e.g. `decode_token` exception in `refresh()` and `logout()`) — these are not currently instrumented with `# Plan 11 adds:` stubs. The caller receives a 401 and the structlog warning from Plan 05/06 is sufficient; formal audit writes for these edge cases are left for a future hardening pass.
- **Email addresses in audit for anonymous login_failed events** — logged in `after_state["email"]` for security incident review; confirm with your privacy/compliance team if this conflicts with local data-protection requirements before deploying.

---

Say "proceed" for Plan 12 (boot-check flip — default auth mode to `jwt`, production startup enforcement, CLAUDE.md IAM contracts).
