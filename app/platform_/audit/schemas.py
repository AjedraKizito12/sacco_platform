"""Pydantic types for the audit-log query endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditEntryOut(BaseModel):
    id: uuid.UUID
    table_name: str
    record_id: uuid.UUID
    operation: str
    actor_type: str
    actor_id: uuid.UUID | None
    actor_label: str | None
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    occurred_at: datetime
    request_id: str | None
    impersonation_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class AuditLogPage(BaseModel):
    items: list[AuditEntryOut]
    total: int
    page: int
    page_size: int
