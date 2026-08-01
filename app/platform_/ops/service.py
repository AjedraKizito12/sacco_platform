"""Read/trigger operations over backup telemetry tables.

OpsService is the ONLY app-side writer of backup_verifications (via
request_verification). backup_runs are written exclusively by the backup
container's scripts; the app only reads them.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.platform_.ops.models import BackupRun, BackupVerification

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class VerificationInProgress(Exception):
    """A verification is already requested or running."""


class OpsService:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def list_recent_runs(self, *, limit: int = 20) -> list[BackupRun]:
        q = select(BackupRun).order_by(BackupRun.created_at.desc()).limit(limit)
        return list((await self._db.execute(q)).scalars())

    async def latest_verification(self) -> BackupVerification | None:
        q = (
            select(BackupVerification)
            .order_by(BackupVerification.created_at.desc())
            .limit(1)
        )
        return (await self._db.execute(q)).scalars().first()

    async def last_verified_at(self) -> datetime | None:
        q = (
            select(BackupVerification.finished_at)
            .where(BackupVerification.status == "passed")
            .order_by(BackupVerification.finished_at.desc())
            .limit(1)
        )
        return (await self._db.execute(q)).scalars().first()

    async def request_verification(
        self, *, requested_by: uuid.UUID
    ) -> BackupVerification:
        pending = (
            select(BackupVerification.id)
            .where(BackupVerification.status.in_(("requested", "running")))
            .limit(1)
        )
        if (await self._db.execute(pending)).scalars().first() is not None:
            raise VerificationInProgress
        row = BackupVerification(requested_by=requested_by, status="requested")
        self._db.add(row)
        await self._db.flush()
        await self._db.refresh(row)
        return row
