"""FastAPI router for the audit-log query endpoints (platform + tenant schema)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.models import PlatformAuditLog, TenantAuditLog
from app.core.db import (
    get_platform_session,
    get_session_for_tenant_schema,
    get_tenant_session,
)
from app.modules.iam.dependencies import CurrentTenantUser
from app.platform_.audit.schemas import AuditEntryOut, AuditLogPage
from app.platform_.audit.service import AuditQueryService
from app.platform_.auth import CurrentAdmin

router = APIRouter(tags=["platform-audit"])
tenant_router = APIRouter(tags=["audit"])

PlatformSession = Annotated[AsyncSession, Depends(get_platform_session)]
TenantSchemaSession = Annotated[AsyncSession, Depends(get_session_for_tenant_schema)]
TenantSession = Annotated[AsyncSession, Depends(get_tenant_session)]


def _page(rows: list[Any], total: int, page: int, page_size: int) -> AuditLogPage:
    return AuditLogPage(
        items=[AuditEntryOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/platform/audit-log", response_model=AuditLogPage)
async def list_platform_audit(
    session: PlatformSession,
    _user: CurrentAdmin,
    table_name: str | None = Query(None),
    record_id: uuid.UUID | None = Query(None),
    actor_id: uuid.UUID | None = Query(None),
    actor_type: str | None = Query(None),
    operation: str | None = Query(None),
    occurred_from: datetime | None = Query(None),
    occurred_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> AuditLogPage:
    rows, total = await AuditQueryService(session, PlatformAuditLog).query(
        table_name=table_name,
        record_id=record_id,
        actor_id=actor_id,
        actor_type=actor_type,
        operation=operation,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        page=page,
        page_size=page_size,
    )
    return _page(rows, total, page, page_size)


@router.get("/platform/tenants/{tenant_id}/audit-log", response_model=AuditLogPage)
async def list_tenant_audit(
    tenant_id: uuid.UUID,
    session: TenantSchemaSession,
    _user: CurrentAdmin,
    table_name: str | None = Query(None),
    record_id: uuid.UUID | None = Query(None),
    actor_id: uuid.UUID | None = Query(None),
    actor_type: str | None = Query(None),
    operation: str | None = Query(None),
    occurred_from: datetime | None = Query(None),
    occurred_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> AuditLogPage:
    rows, total = await AuditQueryService(session, TenantAuditLog).query(
        table_name=table_name,
        record_id=record_id,
        actor_id=actor_id,
        actor_type=actor_type,
        operation=operation,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        page=page,
        page_size=page_size,
    )
    return _page(rows, total, page, page_size)


@tenant_router.get("/audit-log", response_model=AuditLogPage)
async def list_operator_audit(
    session: TenantSession,
    _user: CurrentTenantUser,
    table_name: str | None = Query(None),
    record_id: uuid.UUID | None = Query(None),
    actor_id: uuid.UUID | None = Query(None),
    actor_type: str | None = Query(None),
    operation: str | None = Query(None),
    occurred_from: datetime | None = Query(None),
    occurred_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> AuditLogPage:
    rows, total = await AuditQueryService(session, TenantAuditLog).query(
        table_name=table_name,
        record_id=record_id,
        actor_id=actor_id,
        actor_type=actor_type,
        operation=operation,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        page=page,
        page_size=page_size,
    )
    return _page(rows, total, page, page_size)
