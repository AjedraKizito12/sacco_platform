import os
from collections.abc import AsyncGenerator

import pytest
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://sacco:sacco@localhost:5432/sacco_test")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-not-used-in-production")

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

    yield engine

    try:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA IF EXISTS {TEST_TENANT_SCHEMA} CASCADE"))
            await conn.execute(text("DROP SCHEMA IF EXISTS platform CASCADE"))
    finally:
        await engine.dispose()


@pytest.fixture
async def platform_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Rolled-back platform session per test."""
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session:  # noqa: SIM117
        async with session.begin():
            await session.execute(text("SET LOCAL search_path TO platform"))
            session.sync_session.info["is_platform"] = True
            yield session
            await session.rollback()


@pytest.fixture
async def tenant_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Rolled-back tenant session per test."""
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session:  # noqa: SIM117
        async with session.begin():
            await session.execute(
                text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform")
            )
            yield session
            await session.rollback()
