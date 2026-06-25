import base64
import os
import uuid
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

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-not-used-in-production")
os.environ.setdefault("PLATFORM_BOOTSTRAP_EMAIL", "admin@test.example")
# Force stub mode regardless of shell env or .env file — tests are written for stub auth.
os.environ["PLATFORM_AUTH_MODE"] = "stub"
os.environ["TENANT_AUTH_MODE"] = "stub"
os.environ["MEMBER_AUTH_MODE"] = "stub"
os.environ.setdefault("JWT_KEK", base64.b64encode(b"\x01" * 32).decode())

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
    import app.core.outbox.models  # noqa: F401 — registers TenantOutboxEvent/PlatformOutboxEvent in Base.metadata
    import app.modules.credit.models  # noqa: F401 — registers credit tables in Base.metadata
    import app.modules.fees.models  # noqa: F401 — registers fee tables in Base.metadata
    import app.modules.iam.keys.models  # noqa: F401 — registers JwtSigningKey in Base.metadata
    import app.modules.iam.sessions.models  # noqa: F401 — registers PlatformSession, TenantSession in Base.metadata
    import app.modules.iam.tenant_users.models  # noqa: F401 — registers TenantUser in Base.metadata
    import app.modules.ledger.models  # noqa: F401 — registers ledger tables in Base.metadata
    import app.modules.maker_checker.models.platform  # noqa: F401 — registers platform approval_requests in Base.metadata
    import app.modules.maker_checker.models.tenant  # noqa: F401 — registers approval_requests in Base.metadata
    import app.modules.members.models  # noqa: F401 — registers members table in Base.metadata
    import app.modules.reporting.models  # noqa: F401 — registers reporting tables in Base.metadata
    import app.modules.savings.models  # noqa: F401 — registers savings tables in Base.metadata
    import app.modules.shares.models  # noqa: F401 — registers shares tables in Base.metadata
    import app.platform_.billing.models  # noqa: F401 — registers billing tables in Base.metadata
    import app.platform_.impersonations.models  # noqa: F401 — registers SupportImpersonation in Base.metadata
    import app.platform_.models  # noqa: F401 — registers Tenant, PlatformUser in Base.metadata
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
        # Create tenant sequences that are not part of SQLAlchemy metadata
        await conn.execute(
            text(f"CREATE SEQUENCE IF NOT EXISTS {TEST_TENANT_SCHEMA}.member_number_seq START 1")
        )
        await conn.execute(
            text(f"CREATE SEQUENCE IF NOT EXISTS {TEST_TENANT_SCHEMA}.loan_number_seq START 1")
        )
        await conn.execute(
            text(f"CREATE SEQUENCE IF NOT EXISTS {TEST_TENANT_SCHEMA}.payroll_batch_number_seq START 1")
        )
        # processed_events is Alembic-only DDL (not in Base.metadata) — create manually.
        await conn.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS {TEST_TENANT_SCHEMA}.processed_events ("
                "  event_id UUID NOT NULL,"
                "  consumer_name TEXT NOT NULL,"
                "  processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
                "  PRIMARY KEY (event_id, consumer_name)"
                ")"
            )
        )
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS platform.processed_events ("
                "  event_id UUID NOT NULL,"
                "  consumer_name TEXT NOT NULL,"
                "  processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
                "  PRIMARY KEY (event_id, consumer_name)"
                ")"
            )
        )

    # Repoint app.core.db.AsyncSessionFactory at the test engine so that
    # any code path which opens an internal cross-schema session
    # (e.g. ImpersonationService.mint_tenant_token) uses the same engine
    # the tests are running on. Otherwise the prod engine's pooled
    # connections get bound to a different event loop and asyncpg fails
    # with "Task ... attached to a different loop".
    import app.core.db as _core_db

    _core_db.AsyncSessionFactory = async_sessionmaker(  # type: ignore[assignment]
        engine, expire_on_commit=False
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


@pytest.fixture
async def tenant_actor_id(test_engine: AsyncEngine) -> uuid.UUID:
    """Insert a tenant_users row (idempotent) and return its id.

    Required because CurrentTenantUser (used by every protected route) in
    stub mode validates the X-Tenant-Actor-ID header against this table.
    Module integration-test fixtures should depend on this fixture and pass
    its value as the X-Tenant-Actor-ID header.
    """
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        existing = (
            await session.execute(
                text(
                    "SELECT id FROM tenant_users WHERE email = 'test-actor@example.com'"
                )
            )
        ).scalar()
        if existing is not None:
            return existing
        new_id = uuid.uuid4()
        await session.execute(
            text(
                "INSERT INTO tenant_users "
                "(id, email, full_name, is_active, is_admin, created_at, updated_at) "
                "VALUES (:id, 'test-actor@example.com', 'Test Actor', "
                "true, true, now(), now())"
            ),
            {"id": new_id},
        )
        await session.commit()
        return new_id
