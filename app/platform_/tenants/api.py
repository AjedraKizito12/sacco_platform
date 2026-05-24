"""FastAPI router for /platform/tenants."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_platform_session
from app.modules.maker_checker.registry import approval_executor
from app.platform_.auth import get_current_platform_user, get_current_superuser
from app.platform_.models import PlatformUser
from app.platform_.provisioning.tasks import provision_tenant
from app.platform_.tenants.schemas import (
    CreateTenantRequest,
    TenantCreateResponse,
    TenantOut,
)
from app.platform_.tenants.service import TenantService

router = APIRouter(prefix="/platform/tenants", tags=["platform-tenants"])

Session = Annotated[AsyncSession, Depends(get_platform_session)]
AnyPlatformUser = Annotated[PlatformUser, Depends(get_current_platform_user)]
Superuser = Annotated[PlatformUser, Depends(get_current_superuser)]


@approval_executor("tenant.retry_provisioning")  # type: ignore[misc]
async def _execute_retry_provisioning(session: AsyncSession, payload: dict) -> dict:  # type: ignore[type-arg]
    provision_tenant.delay(payload["tenant_id"])
    return {"dispatched": True}


@router.post("", response_model=TenantCreateResponse, status_code=202)
async def create_tenant(
    body: CreateTenantRequest,
    session: Session,
    actor: Superuser,
) -> TenantCreateResponse:
    svc = TenantService(session)
    try:
        tenant = await svc.create(slug=body.slug, name=body.name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()

    provision_tenant.delay(str(tenant.id), body.admin_email)

    return TenantCreateResponse(
        tenant=TenantOut.model_validate(tenant),
        status_url=f"/platform/tenants/{tenant.id}",
    )


@router.get("", response_model=list[TenantOut])
async def list_tenants(
    session: Session,
    actor: AnyPlatformUser,
    status: str | None = Query(None),
) -> list[TenantOut]:
    svc = TenantService(session)
    tenants = await svc.list_tenants(status=status)
    return [TenantOut.model_validate(t) for t in tenants]


@router.get("/{tenant_id}", response_model=TenantOut)
async def get_tenant(
    tenant_id: uuid.UUID,
    session: Session,
    actor: AnyPlatformUser,
) -> TenantOut:
    svc = TenantService(session)
    tenant = await svc.get(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return TenantOut.model_validate(tenant)


@router.post("/{tenant_id}/retry-provisioning", response_model=TenantOut)
async def retry_provisioning(
    tenant_id: uuid.UUID,
    session: Session,
    actor: Superuser,
) -> TenantOut:
    """Retry a failed provisioning. Requires maker-checker approval."""
    from app.modules.maker_checker.service import ApprovalService

    svc = TenantService(session)
    try:
        tenant = await svc.mark_retry(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    approval_svc = ApprovalService(session)
    await approval_svc.submit(
        operation_type="tenant.retry_provisioning",
        payload={"tenant_id": str(tenant_id)},
        requested_by=actor.id,
        required_approvals=1,
    )
    await session.commit()
    return TenantOut.model_validate(tenant)
