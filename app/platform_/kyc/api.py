from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_platform_session, get_session_for_tenant_schema
from app.modules.organization.schemas import OrganizationKycOut
from app.modules.organization.service import KycIncomplete, OrganizationKycService
from app.platform_.auth import CurrentAdmin
from app.platform_.kyc.schemas import SaccoKycRequirementsIn, SaccoKycRequirementsOut
from app.platform_.kyc.service import SaccoKycRequirementsService

router = APIRouter(prefix="/platform", tags=["platform-kyc"])

PlatformSession = Annotated[AsyncSession, Depends(get_platform_session)]
TenantSchemaSession = Annotated[AsyncSession, Depends(get_session_for_tenant_schema)]


@router.get("/kyc/sacco-requirements", response_model=SaccoKycRequirementsOut)
async def get_sacco_requirements(
    session: PlatformSession, _user: CurrentAdmin
) -> SaccoKycRequirementsOut:
    config = await SaccoKycRequirementsService(session).list_config()
    return SaccoKycRequirementsOut.from_config(config)


@router.put("/kyc/sacco-requirements", response_model=SaccoKycRequirementsOut)
async def put_sacco_requirements(
    body: SaccoKycRequirementsIn, session: PlatformSession, _user: CurrentAdmin
) -> SaccoKycRequirementsOut:
    svc = SaccoKycRequirementsService(session)
    await svc.replace(body.required)
    config = await svc.list_config()
    return SaccoKycRequirementsOut.from_config(config)


@router.get("/tenants/{tenant_id}/kyc", response_model=OrganizationKycOut)
async def get_tenant_kyc(
    tenant_id: uuid.UUID,  # noqa: ARG001 — consumed by the dep
    session: TenantSchemaSession,
    _user: CurrentAdmin,
) -> OrganizationKycOut:
    row, completion = await OrganizationKycService(session).get_with_completion()
    return OrganizationKycOut.from_row_and_completion(row, completion)


@router.post("/tenants/{tenant_id}/kyc/verify", response_model=OrganizationKycOut)
async def verify_tenant_kyc(
    tenant_id: uuid.UUID,  # noqa: ARG001 — consumed by the dep
    session: TenantSchemaSession,
    user: CurrentAdmin,
) -> OrganizationKycOut:
    svc = OrganizationKycService(session)
    try:
        await svc.set_verified(verified=True, platform_user_id=user.id)
    except KycIncomplete as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    row, completion = await svc.get_with_completion()
    return OrganizationKycOut.from_row_and_completion(row, completion)


@router.post("/tenants/{tenant_id}/kyc/unverify", response_model=OrganizationKycOut)
async def unverify_tenant_kyc(
    tenant_id: uuid.UUID,  # noqa: ARG001 — consumed by the dep
    session: TenantSchemaSession,
    _user: CurrentAdmin,
) -> OrganizationKycOut:
    svc = OrganizationKycService(session)
    await svc.set_verified(verified=False, platform_user_id=None)
    row, completion = await svc.get_with_completion()
    return OrganizationKycOut.from_row_and_completion(row, completion)
