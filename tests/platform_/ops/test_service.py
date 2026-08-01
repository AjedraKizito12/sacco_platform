from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.platform_.ops.models import BackupVerification
from app.platform_.ops.service import OpsService, VerificationInProgress


@pytest.mark.asyncio
async def test_last_verified_at_returns_latest_passed(test_engine):
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    ids: list[uuid.UUID] = []
    newer = datetime.now(UTC)
    older = newer - timedelta(days=2)
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        old = BackupVerification(status="passed", started_at=older, finished_at=older)
        new = BackupVerification(status="passed", started_at=newer, finished_at=newer)
        failed = BackupVerification(
            status="failed", started_at=newer, finished_at=newer
        )
        s.add_all([old, new, failed])
        await s.flush()
        ids.extend([old.id, new.id, failed.id])
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            got = await OpsService(s).last_verified_at()
            assert got is not None
            # Must be the most recent PASSED row, not the failed one.
            assert abs((got - newer).total_seconds()) < 1
    finally:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            await s.execute(
                text("DELETE FROM platform.backup_verifications WHERE id = ANY(:ids)"),
                {"ids": ids},
            )


@pytest.mark.asyncio
async def test_last_verified_at_none_when_no_passed(test_engine):
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    ids: list[uuid.UUID] = []
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        failed = BackupVerification(
            status="failed",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
        s.add(failed)
        await s.flush()
        ids.append(failed.id)
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            assert await OpsService(s).last_verified_at() is None
    finally:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            await s.execute(
                text("DELETE FROM platform.backup_verifications WHERE id = ANY(:ids)"),
                {"ids": ids},
            )


@pytest.mark.asyncio
async def test_request_verification_creates_requested_row(test_engine):
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    made: list[uuid.UUID] = []
    actor = uuid.uuid4()
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            row = await OpsService(s).request_verification(requested_by=actor)
            await s.commit()
            made.append(row.id)
            assert row.status == "requested"
            assert row.requested_by == actor
    finally:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            await s.execute(
                text("DELETE FROM platform.backup_verifications WHERE id = ANY(:ids)"),
                {"ids": made},
            )


@pytest.mark.asyncio
async def test_request_verification_conflicts_when_pending(test_engine):
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    made: list[uuid.UUID] = []
    actor = uuid.uuid4()
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            row = await OpsService(s).request_verification(requested_by=actor)
            await s.commit()
            made.append(row.id)
            assert row.status == "requested"
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            with pytest.raises(VerificationInProgress):
                await OpsService(s).request_verification(requested_by=actor)
    finally:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            await s.execute(
                text("DELETE FROM platform.backup_verifications WHERE id = ANY(:ids)"),
                {"ids": made},
            )
