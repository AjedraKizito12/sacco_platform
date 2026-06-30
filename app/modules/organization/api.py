from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_tenant_session
from app.modules.iam.dependencies import CurrentTenantUser
from app.modules.organization.schemas import OrganizationKycOut, OrganizationKycValuesIn
from app.modules.organization.service import OrganizationKycService

router = APIRouter(prefix="/organization", tags=["organization"])

Session = Annotated[AsyncSession, Depends(get_tenant_session)]


@router.get("/kyc", response_model=OrganizationKycOut)
async def get_organization_kyc(
    session: Session, _user: CurrentTenantUser
) -> OrganizationKycOut:
    row, completion = await OrganizationKycService(session).get_with_completion()
    return OrganizationKycOut.from_row_and_completion(row, completion)


@router.put("/kyc", response_model=OrganizationKycOut)
async def put_organization_kyc(
    body: OrganizationKycValuesIn, session: Session, _user: CurrentTenantUser
) -> OrganizationKycOut:
    row, completion = await OrganizationKycService(session).upsert(
        body.model_dump(exclude_unset=True)
    )
    return OrganizationKycOut.from_row_and_completion(row, completion)
