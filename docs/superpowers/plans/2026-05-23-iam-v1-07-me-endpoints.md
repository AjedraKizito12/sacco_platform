# IAM v1-07: /me Endpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `GET /platform/auth/me` and `GET /auth/me` — both return the authenticated user's profile from a valid Bearer access token, verifying the session is non-revoked before returning.

**Architecture:** Each endpoint adds a `me(access_token)` method to the existing `PlatformAuthService` and `TenantAuthService` respectively (in-place modification of Plan 05/06 files). The method decodes the token, checks the session row is non-revoked, fetches the user by `sub` claim, and returns it. A new `TenantUserOut` schema is added to `app/modules/iam/tenant_auth/schemas.py`. `PlatformUserOut` already exists in `app/platform_/users/schemas.py` and is reused as-is. No new files are created.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, PyJWT, pytest-anyio, httpx

---

## Required Reading (complete before starting any task)

1. `CLAUDE.md` — architectural rules
2. `docs/superpowers/specs/2026-05-21-iam-v1-design.md` §7.1 (`GET /platform/auth/me`) and §7.2 (`GET /auth/me`)
3. `app/modules/iam/platform_auth/service.py` — `PlatformAuthService` (add `me()` here)
4. `app/modules/iam/platform_auth/api.py` — existing platform auth router (add endpoint here)
5. `app/modules/iam/tenant_auth/service.py` — `TenantAuthService` (add `me()` here)
6. `app/modules/iam/tenant_auth/api.py` — existing tenant auth router (add endpoint here)
7. `app/modules/iam/tenant_auth/schemas.py` — add `TenantUserOut` here
8. `app/platform_/users/schemas.py` — `PlatformUserOut` (already has all needed fields)
9. `app/modules/iam/tenant_users/models.py` — `TenantUser` column layout (Plan 04)
10. `tests/modules/iam/platform_auth/test_platform_auth_service.py` — existing test file (append to it)
11. `tests/modules/iam/platform_auth/test_platform_auth_api.py` — existing API test file (append to it)
12. `tests/modules/iam/tenant_auth/test_tenant_auth_service.py` — existing test file (append to it)
13. `tests/modules/iam/tenant_auth/test_tenant_auth_api.py` — existing API test file (append to it)

---

## File Map

```
MODIFY app/modules/iam/tenant_auth/schemas.py              — add TenantUserOut
MODIFY app/modules/iam/platform_auth/service.py            — add me() method
MODIFY app/modules/iam/platform_auth/api.py                — add GET /platform/auth/me
MODIFY app/modules/iam/tenant_auth/service.py              — add me() method
MODIFY app/modules/iam/tenant_auth/api.py                  — add GET /auth/me
MODIFY tests/modules/iam/platform_auth/test_platform_auth_service.py  — append me() tests
MODIFY tests/modules/iam/platform_auth/test_platform_auth_api.py      — append me API tests
MODIFY tests/modules/iam/tenant_auth/test_tenant_auth_service.py      — append me() tests
MODIFY tests/modules/iam/tenant_auth/test_tenant_auth_api.py          — append me API tests
```

---

### Task 1: TenantUserOut schema

**Files:**
- Modify: `app/modules/iam/tenant_auth/schemas.py`

`TenantUserOut` is an output-only schema. It intentionally omits `hashed_password`.

- [ ] **Step 1: Append `TenantUserOut` to `app/modules/iam/tenant_auth/schemas.py`**

Add after the existing `TenantTokenResponse` class:

```python
import uuid
from datetime import datetime


class TenantUserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}
```

> Also add `import uuid` and `from datetime import datetime` at the top of the file if not already present.

- [ ] **Step 2: Verify the schema parses cleanly**

```bash
python -c "
import uuid
from datetime import datetime, UTC
from app.modules.iam.tenant_auth.schemas import TenantUserOut
out = TenantUserOut(
    id=uuid.uuid4(), email='a@b.com', full_name='Test',
    is_active=True, is_admin=False,
    created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
)
assert out.last_login_at is None
print('TenantUserOut OK')
"
```

Expected: `TenantUserOut OK`

- [ ] **Step 3: Commit**

```bash
git add app/modules/iam/tenant_auth/schemas.py
git commit -m "feat(iam): TenantUserOut schema"
```

---

### Task 2: `PlatformAuthService.me()` and `GET /platform/auth/me`

**Files:**
- Modify: `app/modules/iam/platform_auth/service.py`
- Modify: `app/modules/iam/platform_auth/api.py`
- Modify: `tests/modules/iam/platform_auth/test_platform_auth_service.py`
- Modify: `tests/modules/iam/platform_auth/test_platform_auth_api.py`

- [ ] **Step 1: Write the failing service tests**

Append to `tests/modules/iam/platform_auth/test_platform_auth_service.py`:

```python
# ── me ────────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_me_returns_current_user(platform_session, mock_key_service, active_user):
    svc = _make_service(platform_session, mock_key_service)
    login_resp = await svc.login(
        email=active_user.email, password=_PASSWORD,
        user_agent=None, ip_address=None,
    )
    user = await svc.me(login_resp.access_token)
    assert user.id == active_user.id
    assert user.email == active_user.email


@pytest.mark.anyio
async def test_me_with_invalid_token_raises_401(platform_session, mock_key_service):
    from fastapi import HTTPException

    svc = _make_service(platform_session, mock_key_service)
    with pytest.raises(HTTPException) as exc_info:
        await svc.me("not.a.valid.jwt")
    assert exc_info.value.status_code == 401


@pytest.mark.anyio
async def test_me_after_logout_raises_401(platform_session, mock_key_service, active_user):
    """After logout the session is revoked; me() must reject the old access token."""
    from fastapi import HTTPException

    svc = _make_service(platform_session, mock_key_service)
    login_resp = await svc.login(
        email=active_user.email, password=_PASSWORD,
        user_agent=None, ip_address=None,
    )
    await svc.logout(login_resp.access_token)

    with pytest.raises(HTTPException) as exc_info:
        await svc.me(login_resp.access_token)
    assert exc_info.value.status_code == 401
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/iam/platform_auth/test_platform_auth_service.py -v -k "test_me"
```

Expected: `AttributeError` — `PlatformAuthService` has no `me` method yet

- [ ] **Step 3: Add `me()` to `app/modules/iam/platform_auth/service.py`**

Add the following method inside the `PlatformAuthService` class body, after `logout()`:

```python
    # ── me ────────────────────────────────────────────────────────────────

    async def me(self, access_token: str) -> PlatformUser:
        """Return the authenticated PlatformUser for the given access token.

        Decodes the token, verifies the session is not revoked, then fetches
        and returns the user row. The caller (API layer) converts it to
        PlatformUserOut.

        Raises:
            HTTPException 401: invalid/expired token, revoked session, or
                               user not found.
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
        sub = claims.get("sub")
        if not session_id_str or not sub:
            raise HTTPException(status_code=401, detail="Malformed token claims")

        try:
            session_id = uuid.UUID(session_id_str)
            user_id = uuid.UUID(sub)
        except ValueError:
            raise HTTPException(status_code=401, detail="Malformed token claims")

        # Verify session is not revoked (revocation takes effect immediately).
        session_row = await self._session_svc.get_by_session_id(session_id)
        if session_row is None or session_row.revoked_at is not None:
            raise HTTPException(status_code=401, detail="Session not found or revoked")

        result = await self._db.execute(
            select(PlatformUser).where(PlatformUser.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")

        # Plan 11 adds: audit("platform_auth.me", user_id=str(user.id))

        return user
```

- [ ] **Step 4: Run service tests to confirm pass**

```bash
pytest tests/modules/iam/platform_auth/test_platform_auth_service.py -v -k "test_me"
```

Expected: 3 tests PASS

- [ ] **Step 5: Write the failing API tests**

Append to `tests/modules/iam/platform_auth/test_platform_auth_api.py`:

```python
# ── GET /platform/auth/me ─────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_platform_me_returns_200_with_user():
    import uuid
    from datetime import UTC, datetime
    from app.modules.iam.platform_auth.api import get_platform_auth_service
    from app.platform_.models import PlatformUser

    fake_user = PlatformUser(
        id=uuid.uuid4(),
        email="me@example.com",
        full_name="Me User",
        is_active=True,
        is_superuser=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_login_at=None,
    )
    mock_svc = AsyncMock()
    mock_svc.me = AsyncMock(return_value=fake_user)

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/platform/auth/me",
                headers={"Authorization": "Bearer valid.access.token"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "me@example.com"
        assert body["full_name"] == "Me User"
        assert "hashed_password" not in body
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)


@pytest.mark.anyio
async def test_platform_me_returns_401_without_bearer():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/platform/auth/me")
    assert resp.status_code in (401, 403)


@pytest.mark.anyio
async def test_platform_me_returns_401_for_revoked_session():
    from app.modules.iam.platform_auth.api import get_platform_auth_service

    mock_svc = AsyncMock()
    mock_svc.me = AsyncMock(
        side_effect=HTTPException(status_code=401, detail="Session not found or revoked")
    )

    app.dependency_overrides[get_platform_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/platform/auth/me",
                headers={"Authorization": "Bearer revoked.token"},
            )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_platform_auth_service, None)
```

- [ ] **Step 6: Run API tests to confirm failure**

```bash
pytest tests/modules/iam/platform_auth/test_platform_auth_api.py -v -k "test_platform_me"
```

Expected: 404 — the route does not exist yet

- [ ] **Step 7: Add `GET /platform/auth/me` to `app/modules/iam/platform_auth/api.py`**

Add this import at the top of the file (alongside existing imports):

```python
from app.platform_.users.schemas import PlatformUserOut
```

Then append this route at the bottom of the router definitions, after the `platform_logout` route:

```python
@router.get("/me", response_model=PlatformUserOut)
async def platform_me(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    svc: PlatformAuth,
) -> PlatformUserOut:
    """Return the current platform user's profile from a valid Bearer access token."""
    user = await svc.me(credentials.credentials)
    return PlatformUserOut.model_validate(user)
```

- [ ] **Step 8: Run all platform auth tests to confirm pass**

```bash
pytest tests/modules/iam/platform_auth/ -v
```

Expected: all tests PASS (previous tests unaffected)

- [ ] **Step 9: Commit**

```bash
git add app/modules/iam/platform_auth/service.py \
        app/modules/iam/platform_auth/api.py \
        tests/modules/iam/platform_auth/test_platform_auth_service.py \
        tests/modules/iam/platform_auth/test_platform_auth_api.py
git commit -m "feat(iam): GET /platform/auth/me — return current platform user"
```

---

### Task 3: `TenantAuthService.me()` and `GET /auth/me`

**Files:**
- Modify: `app/modules/iam/tenant_auth/service.py`
- Modify: `app/modules/iam/tenant_auth/api.py`
- Modify: `tests/modules/iam/tenant_auth/test_tenant_auth_service.py`
- Modify: `tests/modules/iam/tenant_auth/test_tenant_auth_api.py`

- [ ] **Step 1: Write the failing service tests**

Append to `tests/modules/iam/tenant_auth/test_tenant_auth_service.py`:

```python
# ── me ────────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_tenant_me_returns_current_user(
    tenant_session, mock_key_service, active_tenant_user
):
    svc = _make_service(tenant_session, mock_key_service)
    login_resp = await svc.login(
        email=active_tenant_user.email, password=_PASSWORD,
        user_agent=None, ip_address=None,
    )
    user = await svc.me(login_resp.access_token)
    assert user.id == active_tenant_user.id
    assert user.email == active_tenant_user.email


@pytest.mark.anyio
async def test_tenant_me_with_invalid_token_raises_401(tenant_session, mock_key_service):
    from fastapi import HTTPException

    svc = _make_service(tenant_session, mock_key_service)
    with pytest.raises(HTTPException) as exc_info:
        await svc.me("not.a.valid.jwt")
    assert exc_info.value.status_code == 401


@pytest.mark.anyio
async def test_tenant_me_after_logout_raises_401(
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
        await svc.me(login_resp.access_token)
    assert exc_info.value.status_code == 401
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/iam/tenant_auth/test_tenant_auth_service.py -v -k "test_tenant_me"
```

Expected: `AttributeError` — `TenantAuthService` has no `me` method yet

- [ ] **Step 3: Add `me()` to `app/modules/iam/tenant_auth/service.py`**

Add this import at the top of `tenant_auth/service.py` (alongside existing imports):

```python
from app.modules.iam.tenant_users.models import TenantUser  # already imported
```

(It's already imported for the login query — no new import needed. Just verify it's there.)

Then add the following method inside the `TenantAuthService` class body, after `logout()`:

```python
    # ── me ────────────────────────────────────────────────────────────────

    async def me(self, access_token: str) -> TenantUser:
        """Return the authenticated TenantUser for the given access token.

        Decodes the token using the tenant-specific audience ("tenant:<slug>"),
        verifies the session is not revoked, and returns the user row.
        The caller (API layer) converts it to TenantUserOut.

        Raises:
            HTTPException 401: invalid/expired token, revoked session, or
                               user not found.
        """
        try:
            claims = await decode_token(
                token=access_token,
                audience=self._audience,
                key_service=self._key_service,
            )
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid or expired access token")

        session_id_str = claims.get("session_id")
        sub = claims.get("sub")
        if not session_id_str or not sub:
            raise HTTPException(status_code=401, detail="Malformed token claims")

        try:
            session_id = uuid.UUID(session_id_str)
            user_id = uuid.UUID(sub)
        except ValueError:
            raise HTTPException(status_code=401, detail="Malformed token claims")

        session_row = await self._session_svc.get_by_session_id(session_id)
        if session_row is None or session_row.revoked_at is not None:
            raise HTTPException(status_code=401, detail="Session not found or revoked")

        result = await self._db.execute(
            select(TenantUser).where(TenantUser.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")

        # Plan 11 adds: audit("tenant_auth.me", user_id=str(user.id))

        return user
```

> Also verify that `select` is imported at the top of `tenant_auth/service.py` — it was used in `login()` so it should already be there.

- [ ] **Step 4: Run service tests to confirm pass**

```bash
pytest tests/modules/iam/tenant_auth/test_tenant_auth_service.py -v -k "test_tenant_me"
```

Expected: 3 tests PASS

- [ ] **Step 5: Write the failing API tests**

Append to `tests/modules/iam/tenant_auth/test_tenant_auth_api.py`:

```python
# ── GET /auth/me ──────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_tenant_me_returns_200_with_user():
    import uuid
    from datetime import UTC, datetime
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service
    from app.modules.iam.tenant_users.models import TenantUser

    fake_user = TenantUser(
        id=uuid.uuid4(),
        email="member@sacco.org",
        full_name="SACCO Member",
        is_active=True,
        is_admin=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    mock_svc = AsyncMock()
    mock_svc.me = AsyncMock(return_value=fake_user)

    app.dependency_overrides[get_tenant_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/auth/me",
                headers={**_SLUG_HEADER, "Authorization": "Bearer valid.access.token"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "member@sacco.org"
        assert body["full_name"] == "SACCO Member"
        assert "hashed_password" not in body
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)


@pytest.mark.anyio
async def test_tenant_me_returns_401_without_bearer():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/auth/me", headers=_SLUG_HEADER)
    assert resp.status_code in (401, 403)


@pytest.mark.anyio
async def test_tenant_me_returns_401_for_revoked_session():
    from app.modules.iam.tenant_auth.api import get_tenant_auth_service

    mock_svc = AsyncMock()
    mock_svc.me = AsyncMock(
        side_effect=HTTPException(
            status_code=401, detail="Session not found or revoked"
        )
    )

    app.dependency_overrides[get_tenant_auth_service] = lambda: mock_svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/auth/me",
                headers={**_SLUG_HEADER, "Authorization": "Bearer revoked.token"},
            )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_tenant_auth_service, None)
```

- [ ] **Step 6: Run API tests to confirm failure**

```bash
pytest tests/modules/iam/tenant_auth/test_tenant_auth_api.py -v -k "test_tenant_me"
```

Expected: 404 — the route does not exist yet

- [ ] **Step 7: Add `GET /auth/me` to `app/modules/iam/tenant_auth/api.py`**

Add this import at the top of `tenant_auth/api.py` (alongside existing imports):

```python
from app.modules.iam.tenant_auth.schemas import TenantUserOut
```

> `TenantRefreshRequest`, `TenantLoginRequest`, and `TenantTokenResponse` are already imported. Add `TenantUserOut` to the same `from` statement:
> ```python
> from app.modules.iam.tenant_auth.schemas import (
>     TenantLoginRequest,
>     TenantRefreshRequest,
>     TenantTokenResponse,
>     TenantUserOut,
> )
> ```

Then append this route at the bottom of the router definitions, after `tenant_logout`:

```python
@router.get("/me", response_model=TenantUserOut)
async def tenant_me(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    svc: TenantAuth,
) -> TenantUserOut:
    """Return the current tenant user's profile from a valid Bearer access token."""
    user = await svc.me(credentials.credentials)
    return TenantUserOut.model_validate(user)
```

- [ ] **Step 8: Run all tenant auth tests to confirm pass**

```bash
pytest tests/modules/iam/tenant_auth/ -v
```

Expected: all tests PASS

- [ ] **Step 9: Commit**

```bash
git add app/modules/iam/tenant_auth/service.py \
        app/modules/iam/tenant_auth/api.py \
        tests/modules/iam/tenant_auth/test_tenant_auth_service.py \
        tests/modules/iam/tenant_auth/test_tenant_auth_api.py
git commit -m "feat(iam): GET /auth/me — return current tenant user"
```

---

## Verification Criteria

Before marking this plan complete, run the following in order:

```bash
# 1. Linting — zero errors
ruff check app/modules/iam/platform_auth/ app/modules/iam/tenant_auth/

# 2. Type checking — zero errors
mypy app/modules/iam/platform_auth/ app/modules/iam/tenant_auth/ --strict

# 3. Platform auth tests (includes me() service + API tests)
pytest tests/modules/iam/platform_auth/ -v

# 4. Tenant auth tests (includes me() service + API tests)
pytest tests/modules/iam/tenant_auth/ -v

# 5. Full suite — no regressions
pytest tests/ -v
```

All commands must exit cleanly before this plan is considered complete.

---

## What is NOT in this plan

- **Password reset endpoints** — Plan 08 adds `reset_request()` and `reset_confirm()` methods to both services, plus the corresponding API routes.
- **Updating `last_login_at`** on the user row — this belongs in the `login()` method (Plan 05/06). If it was not implemented there, Plan 08 is a good time to add it alongside the rehash step: `user.last_login_at = datetime.now(UTC)`.
- **Real JWT-validating `get_current_platform_user` / `get_current_tenant_user`** — replaced in Plan 09 using `decode_token` + session check, the same pattern as `me()` here. Plan 09 workers can use `me()` as the reference implementation.
- **Audit events** for `/me` calls — Plan 11 adds the `audit("platform_auth.me", ...)` and `audit("tenant_auth.me", ...)` calls that are currently stubbed with comments.
