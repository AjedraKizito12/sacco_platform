"""FastAPI router for /platform/tenants."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_platform_session
from app.modules.maker_checker.registry import approval_executor
from app.platform_.auth import get_current_platform_user, get_current_superuser
from app.platform_.billing.exceptions import (
    PlanInactive,
    SubscriptionConflict,
)
from app.platform_.billing.schemas import SubscriptionOut
from app.platform_.billing.services import SubscriptionService
from app.platform_.models import PlatformUser
from app.platform_.provisioning.tasks import provision_tenant
from app.platform_.tenants.schemas import (
    AssignPlanIn,
    CreateTenantRequest,
    TenantCreateResponse,
    TenantOut,
    TenantPatchIn,
    TenantSuspendIn,
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


@router.patch("/{tenant_id}", response_model=TenantOut)
async def patch_tenant(
    tenant_id: uuid.UUID,
    body: TenantPatchIn,
    session: Session,
    actor: AnyPlatformUser,
) -> TenantOut:
    """Edit the tenant's name. Immediate, no maker-checker.

    Slug and schema_name are immutable — they're never updatable via this API.
    """
    svc = TenantService(session)
    try:
        tenant = await svc.update_name(tenant_id=tenant_id, name=body.name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return TenantOut.model_validate(tenant)


@router.post("/{tenant_id}/suspend", status_code=202)
async def suspend_tenant(
    tenant_id: uuid.UUID,
    body: TenantSuspendIn,
    session: Session,
    actor: Superuser,
) -> dict[str, str]:
    """Submit a tenant-suspend approval request.

    Maker-checker required. The executor at @approval_executor("tenant.suspend")
    runs on approval and flips status + is_active + subscription_status.
    """
    from app.modules.maker_checker.service import ApprovalService

    tenant = await TenantService(session).get(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if tenant.status == "suspended":
        raise HTTPException(
            status_code=409,
            detail="Tenant is already suspended",
        )

    approval = await ApprovalService(session).submit(
        operation_type="tenant.suspend",
        payload={"tenant_id": str(tenant_id), "reason": body.reason},
        requested_by=actor.id,
    )
    await session.commit()
    return {
        "status": "pending_approval",
        "approval_request_id": str(approval.id),
    }


@router.post("/{tenant_id}/reactivate", response_model=TenantOut)
async def reactivate_tenant(
    tenant_id: uuid.UUID,
    session: Session,
    actor: Superuser,
) -> TenantOut:
    """Restore a suspended tenant. Direct (no maker-checker).

    Returns 409 if the tenant is not currently suspended.
    """
    svc = TenantService(session)
    try:
        tenant = await svc.reactivate(tenant_id=tenant_id)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=409, detail=msg) from exc
    await session.commit()
    return TenantOut.model_validate(tenant)


@router.post(
    "/{tenant_id}/assign-plan",
    response_model=SubscriptionOut,
    status_code=201,
)
async def assign_plan(
    tenant_id: uuid.UUID,
    body: AssignPlanIn,
    session: Session,
    actor: Superuser,
) -> SubscriptionOut:
    """Assign a billing plan to a tenant. Delegates to SubscriptionService.assign.

    Returns 409 if a live subscription already exists or the plan is inactive.
    """
    start_date = body.start_date.date() if body.start_date is not None else None
    try:
        sub = await SubscriptionService(session).assign(
            tenant_id=tenant_id,
            plan_id=body.plan_id,
            start_date=start_date,
        )
    except PlanInactive as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SubscriptionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return SubscriptionOut.model_validate(sub)
