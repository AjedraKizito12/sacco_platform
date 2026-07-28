from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class BackupRunOut(BaseModel):
    id: uuid.UUID
    backup_type: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    repo_size_bytes: int | None
    wal_lag_seconds: int | None
    detail: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


class BackupVerificationOut(BaseModel):
    id: uuid.UUID
    requested_by: uuid.UUID | None
    status: str
    detail: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


class BackupStatusOut(BaseModel):
    recent_runs: list[BackupRunOut]
    latest_verification: BackupVerificationOut | None


class LastVerifiedOut(BaseModel):
    last_verified_at: datetime | None
