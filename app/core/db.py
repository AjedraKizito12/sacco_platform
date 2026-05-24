import re
from collections.abc import AsyncGenerator

import structlog
from fastapi import HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

_SLUG_RE = re.compile(r"^[a-z0-9-]{1,40}$")
_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")

_log = structlog.get_logger(__name__)

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    echo=False,
)

AsyncSessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def _resolve_tenant_schema(slug: str, redis_client: Redis) -> str:
    """Return schema_name for slug, using Redis as a 5-minute cache."""
    cache_key = f"tenant:slug:{slug}:schema"
    cached: bytes | None = await redis_client.get(cache_key)
    if cached is not None:
        return cached.decode()

    # Cache miss: query platform.tenants using a fully-qualified table name
    # so no search_path manipulation is required on this connection.
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT schema_name FROM platform.tenants"
                " WHERE slug = :slug AND is_active = true"
            ),
            {"slug": slug},
        )
        row = result.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{slug}' not found")

    schema_name: str = row[0]
    await redis_client.setex(cache_key, 300, schema_name)
    return schema_name


async def get_tenant_session(
    request: Request,
) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield an AsyncSession scoped to the request tenant.

    Reads the tenant slug from the configured header, looks up schema_name via
    Redis-backed cache, validates it, then executes
    SET LOCAL search_path TO <schema_name>, platform
    before yielding.
    """
    slug: str | None = request.headers.get(settings.tenant_header)
    if not slug:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required header: {settings.tenant_header}",
        )

    if not _SLUG_RE.match(slug):
        raise HTTPException(
            status_code=400,
            detail="Invalid tenant slug: must match ^[a-z0-9-]{1,40}$",
        )

    redis_client: Redis = request.app.state.redis
    schema_name = await _resolve_tenant_schema(slug, redis_client)

    # Defense in depth: validate the schema_name we got from our own DB.
    if not _SCHEMA_RE.match(schema_name):
        _log.error(
            "Resolved schema_name failed validation — possible data corruption",
            slug=slug,
            schema_name=schema_name,
        )
        raise HTTPException(status_code=500, detail="Internal configuration error")

    # schema_name is validated against ^tenant_[a-z0-9_]{1,40}$ — safe to interpolate.
    async with AsyncSessionFactory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_platform_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield an AsyncSession with search_path set to platform."""
    async with AsyncSessionFactory() as session:
        await session.execute(text("SET LOCAL search_path TO platform"))
        session.sync_session.info["is_platform"] = True
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
