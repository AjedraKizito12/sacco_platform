"""Celery beat tasks for JWT signing key lifecycle management.

Tasks run in a synchronous Celery worker context. They bridge into async
code using ``asyncio.run()`` — the same pattern as the outbox relay workers.
A fresh SQLAlchemy engine is created per task invocation (matches the outbox
worker pattern) to avoid connection-pool sharing across Celery processes.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog

from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)


async def _run_advance_lifecycle() -> dict[str, int]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from app.modules.iam.keys.service import KeyService

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            await session.execute(text("SET LOCAL search_path TO platform"))
            svc = KeyService(session)
            now = datetime.now(UTC)
            counts = await svc.advance_lifecycle(now)
            await session.commit()
            _log.info("iam.key_lifecycle_advanced", **counts)
            return counts
    finally:
        await engine.dispose()


async def _run_rotate_if_due() -> dict[str, list[str]]:
    from datetime import timedelta

    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from app.modules.iam.keys.models import JwtSigningKey
    from app.modules.iam.keys.service import KeyService

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    rotated: list[str] = []
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            await session.execute(text("SET LOCAL search_path TO platform"))
            svc = KeyService(session)

            rotation_threshold = datetime.now(UTC) - timedelta(
                days=settings.jwt_key_rotation_days
            )

            for audience in ("platform", "tenant"):
                result = await session.execute(
                    select(JwtSigningKey)
                    .where(JwtSigningKey.audience == audience)
                    .where(JwtSigningKey.status == "active")
                )
                active_key = result.scalar_one_or_none()

                if active_key is None:
                    _log.warning("iam.beat.no_active_key_for_rotation", audience=audience)
                    continue

                if active_key.activated_at and active_key.activated_at <= rotation_threshold:
                    new_key = await svc.rotate(audience=audience)
                    await session.commit()
                    rotated.append(audience)
                    _log.info(
                        "iam.beat.key_rotated",
                        audience=audience,
                        new_kid=new_key.kid,
                    )

        return {"rotated": rotated}
    finally:
        await engine.dispose()


@celery_app.task(name="app.modules.iam.beat.advance_key_lifecycle")  # type: ignore[misc]
def advance_key_lifecycle() -> dict[str, int]:
    """Hourly: advance retiring→retired; soft-delete aged retired keys."""
    return asyncio.run(_run_advance_lifecycle())


@celery_app.task(name="app.modules.iam.beat.rotate_signing_keys_if_due")  # type: ignore[misc]
def rotate_signing_keys_if_due() -> dict[str, list[str]]:
    """Daily: rotate the active key for each audience if it has exceeded JWT_KEY_ROTATION_DAYS."""
    return asyncio.run(_run_rotate_if_due())
