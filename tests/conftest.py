import base64
import os
from collections.abc import AsyncGenerator

import pytest
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-not-used-in-production")
os.environ.setdefault("PLATFORM_BOOTSTRAP_EMAIL", "admin@test.example")
os.environ.setdefault("PLATFORM_AUTH_MODE", "stub")
os.environ.setdefault("JWT_KEK", base64.b64encode(b"\x01" * 32).decode())
os.environ.setdefault("TENANT_AUTH_MODE", "stub")

TEST_TENANT_SCHEMA = "tenant_test"
TEST_TENANT_SLUG = "test-tenant"

# ── structlog: silence during tests unless DEBUG ──────────────────────────────
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(40),  # ERROR level
    logger_factory=structlog.PrintLoggerFactory(),
)


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """One engine per test session. Schemas created once; dropped on teardown."""
    from app.core.db import Base  # noqa: F401 — triggers metadata registration
    import app.modules.iam.keys.models  # noqa: F401 — registers JwtSigningKey in Base.metadata
    import app.modules.iam.sessions.models  # noqa: F401 — registers PlatformSession, TenantSession in Base.metadata
    import app.modules.iam.tenant_users.models  # noqa: F401 — registers TenantUser in Base.metadata
    import app.modules.ledger.models  # noqa: F401 — registers ledger tables in Base.metadata
    import app.modules.members.models  # noqa: F401 — registers members table in Base.metadata

    url = os.environ["DATABASE_URL"]
    engine = create_async_engine(url, echo=False, poolclass=NullPool)

    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS platform"))
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {TEST_TENANT_SCHEMA}"))
        # Platform tables have schema="platform" in __table_args__ → created there.
        # Tenant tables have no schema → created wherever search_path points.
        await conn.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        await conn.run_sync(Base.metadata.create_all)
        # Create tenant sequences that are not part of SQLAlchemy metadata
        await conn.execute(
            text(f"CREATE SEQUENCE IF NOT EXISTS {TEST_TENANT_SCHEMA}.member_number_seq START 1")
        )

    yield engine

    try:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA IF EXISTS {TEST_TENANT_SCHEMA} CASCADE"))
            await conn.execute(text("DROP SCHEMA IF EXISTS platform CASCADE"))
    finally:
        await engine.dispose()


@pytest.fixture
async def platform_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Rolled-back platform session per test.

    Binds the AsyncSession to a single connection whose outer transaction is
    rolled back on teardown. This avoids the asyncpg protocol-state error that
    occurs when session.flush() is called inside a long-lived
    async with session.begin() context in pytest-asyncio ≥0.21 with a
    session-scoped event loop.
    """
    async with test_engine.connect() as conn:
        await conn.begin()
        await conn.execute(text("SET LOCAL search_path TO platform"))
        session = AsyncSession(bind=conn, expire_on_commit=False)
        session.sync_session.info["is_platform"] = True
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()


@pytest.fixture
async def tenant_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Rolled-back tenant session per test.

    Binds the AsyncSession to a single connection whose outer transaction is
    rolled back on teardown. This avoids the asyncpg protocol-state error that
    occurs when session.flush() is called inside a long-lived
    async with session.begin() context in pytest-asyncio ≥0.21 with a
    session-scoped event loop.
    """
    async with test_engine.connect() as conn:
        await conn.begin()
        await conn.execute(
            text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()
