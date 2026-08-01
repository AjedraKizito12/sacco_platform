"""FastAPI router for /platform/ops/backups (superuser-only, direct action)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_platform_session
from app.platform_.auth import CurrentSuperuser
from app.platform_.ops.schemas import (
    BackupRunOut,
    BackupStatusOut,
    BackupVerificationOut,
    LastVerifiedOut,
)
from app.platform_.ops.service import OpsService, VerificationInProgress

router = APIRouter(prefix="/platform/ops", tags=["platform-ops"])

PlatformSession = Annotated[AsyncSession, Depends(get_platform_session)]


@router.get("/backups", response_model=BackupStatusOut)
async def get_backup_status(
    session: PlatformSession, _user: CurrentSuperuser
) -> BackupStatusOut:
    svc = OpsService(session)
    runs = await svc.list_recent_runs()
    latest = await svc.latest_verification()
    return BackupStatusOut(
        recent_runs=[BackupRunOut.model_validate(r) for r in runs],
        latest_verification=(
            BackupVerificationOut.model_validate(latest) if latest else None
        ),
    )


@router.get("/backups/last-verified-at", response_model=LastVerifiedOut)
async def get_last_verified_at(
    session: PlatformSession, _user: CurrentSuperuser
) -> LastVerifiedOut:
    return LastVerifiedOut(
        last_verified_at=await OpsService(session).last_verified_at()
    )


@router.post(
    "/backups/trigger-verification",
    response_model=BackupVerificationOut,
    status_code=status.HTTP_201_CREATED,
)
async def trigger_verification(
    session: PlatformSession, user: CurrentSuperuser
) -> BackupVerificationOut:
    try:
        row = await OpsService(session).request_verification(requested_by=user.id)
    except VerificationInProgress as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A verification is already requested or running.",
        ) from exc
    return BackupVerificationOut.model_validate(row)
