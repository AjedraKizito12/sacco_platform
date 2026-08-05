"""Integration tests for the read-only /platform/rate-limits* endpoints.

Stub platform auth (X-Platform-Actor-ID) + a get_platform_session override
bound to the test engine, mirroring tests/platform_/ops/test_api.py. The live
endpoint peeks per-user buckets straight out of the app's Redis (set up by
lifespan(app)); a separate client seeds one bucket to assert min-remaining
aggregation.
"""
from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.db import get_platform_session
from app.main import app, lifespan
from app.modules.iam.tenant_users.models import TenantUser
from app.platform_.billing.models import SubscriptionPlan
from app.platform_.models import PlatformUser, Tenant

TENANT_SCHEMA = "tenant_test"


def _make_platform_session_override(engine: AsyncEngine):  # type: ignore[no-untyped-def]
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(text("SET LOCAL search_path TO platform"))
            session.sync_session.info["is_platform"] = True
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override


async def _create_platform_user(
    factory: async_sessionmaker[AsyncSession], *, role: str
) -> PlatformUser:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"{role}-{uuid.uuid4().hex[:6]}@test.example",
            full_name="RL Tester",
            is_active=True,
            is_superuser=role == "superuser",
            role=role,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _create_tenant(
    factory: async_sessionmaker[AsyncSession],
) -> Tenant:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        t = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=TENANT_SCHEMA,
            name="Live Test SACCO",
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(t)
    return t


async def _seed_tenant_user(
    factory: async_sessionmaker[AsyncSession],
) -> TenantUser:
    async with factory() as s, s.begin():
        await s.execute(text(f"SET LOCAL search_path TO {TENANT_SCHEMA}, platform"))
        u = TenantUser(
            email=f"u-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Member Staff",
            is_active=True,
            is_admin=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _create_plan_with_overrides(
    factory: async_sessionmaker[AsyncSession], code: str, overrides: dict
) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.add(
            SubscriptionPlan(
                code=code,
                name=f"Plan {code}",
                base_price=0,
                billing_period="monthly",
                features={"rate_limit_overrides": overrides},
                is_active=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.tenants"))
        await s.execute(text("DELETE FROM platform.platform_users"))
        await s.execute(text("DELETE FROM platform.subscription_plans"))
    async with factory() as s, s.begin():
        await s.execute(text(f"SET LOCAL search_path TO {TENANT_SCHEMA}, platform"))
        await s.execute(text("DELETE FROM tenant_users"))


@pytest.fixture
async def client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_platform_session] = _make_platform_session_override(
        test_engine
    )
    try:
        async with lifespan(app), AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c
    except Exception:  # noqa: BLE001, S110
        # Lifespan shutdown races the session-scoped event-loop teardown
        # (redis.aclose() → "Event loop is closed"); harmless, mirrors
        # tests/platform_/ops/test_api.py.
        pass
    finally:
        app.dependency_overrides.pop(get_platform_session, None)


def _hdr(actor_id: uuid.UUID) -> dict[str, str]:
    return {"X-Platform-Actor-ID": str(actor_id)}


class _RedisCtx:
    async def __aenter__(self) -> Redis:
        self._r = Redis.from_url(get_settings().redis_url, decode_responses=False)
        return self._r

    async def __aexit__(self, *exc: object) -> None:
        await self._r.aclose()


async def test_config_returns_defaults_and_plan_overrides(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    admin = await _create_platform_user(factory, role="admin")
    await _create_plan_with_overrides(
        factory, "growth", {"authenticated_default": {"limit": 1000}}
    )
    try:
        r = await client.get("/platform/rate-limits", headers=_hdr(admin.id))
        assert r.status_code == 200, r.text
        body = r.json()
        names = {p["name"] for p in body["defaults"]}
        assert "authenticated_default" in names
        assert "auth_login" in names
        auth_def = next(
            p for p in body["defaults"] if p["name"] == "authenticated_default"
        )
        assert auth_def["limit"] == 300
        assert auth_def["window_seconds"] == 60
        assert body["plan_overrides"]["growth"]["authenticated_default"]["limit"] == 1000
    finally:
        await _cleanup(factory)


async def test_config_requires_admin(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    support = await _create_platform_user(factory, role="support")
    try:
        r = await client.get("/platform/rate-limits", headers=_hdr(support.id))
        assert r.status_code == 403, r.text
    finally:
        await _cleanup(factory)


async def test_tenant_live_returns_min_remaining(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    admin = await _create_platform_user(factory, role="admin")
    tenant = await _create_tenant(factory)
    busy_user = await _seed_tenant_user(factory)
    await _seed_tenant_user(factory)  # untouched → full bucket

    # Seed the busy user's authenticated_default bucket low, in the app's Redis.
    bucket_key = f"rl:authenticated_default:u:tenant:{busy_user.id}"
    async with _RedisCtx() as redis:
        await redis.delete(bucket_key)
        await redis.hset(bucket_key, mapping={"tokens": "5", "ts": str(time.time())})

    try:
        r = await client.get(
            f"/platform/rate-limits/tenants/{tenant.id}/live",
            headers=_hdr(admin.id),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["tenant_id"] == str(tenant.id)
        by_policy = {b["policy"]: b for b in body["buckets"]}
        # Min remaining across the two users for authenticated_default is the
        # busy user's ~5 (the other user's bucket doesn't exist → full 300).
        assert 4 <= by_policy["authenticated_default"]["remaining"] <= 6
        assert by_policy["authenticated_default"]["limit"] == 300
        # A policy no user has touched reports the full limit.
        assert by_policy["reporting"]["remaining"] == 60
    finally:
        async with _RedisCtx() as redis:
            await redis.delete(bucket_key)
        await _cleanup(factory)


async def test_tenant_live_unknown_tenant_404(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    admin = await _create_platform_user(factory, role="admin")
    try:
        r = await client.get(
            f"/platform/rate-limits/tenants/{uuid.uuid4()}/live",
            headers=_hdr(admin.id),
        )
        assert r.status_code == 404, r.text
    finally:
        await _cleanup(factory)
