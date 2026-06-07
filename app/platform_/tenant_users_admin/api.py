"""FastAPI router for /platform/tenants/{tenant_id}/users.

Platform-context endpoints that operate on the tenant schema via the
get_session_for_tenant_schema dep.

Role gate: CurrentAdmin (admin or above). The dep wraps
``get_current_platform_user_with_role("admin")`` so superusers also pass.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_for_tenant_schema
from app.platform_.auth import CurrentAdmin
from app.platform_.tenant_users_admin.schemas import (
    PasswordResetOut,
    TenantUserCreateIn,
    TenantUserCreateOut,
    TenantUserOut,
    TenantUserPatchIn,
)
from app.platform_.tenant_users_admin.service import (
    TenantUserConflict,
    TenantUsersAdminService,
)

router = APIRouter(
    prefix="/platform/tenants/{tenant_id}/users",
    tags=["platform-tenant-users"],
)

# Path-injected cross-schema session.
TenantSchemaSession = Annotated[
    AsyncSession, Depends(get_session_for_tenant_schema)
]


@router.get("", response_model=list[TenantUserOut])
async def list_tenant_users(
    tenant_id: uuid.UUID,  # noqa: ARG001 — consumed by dep injection
    session: TenantSchemaSession,
    _user: CurrentAdmin,
) -> list[TenantUserOut]:
    users = await TenantUsersAdminService(session).list_users()
    return [TenantUserOut.model_validate(u) for u in users]


@router.post(
    "", response_model=TenantUserCreateOut, status_code=status.HTTP_201_CREATED,
)
async def create_tenant_user(
    tenant_id: uuid.UUID,  # noqa: ARG001
    body: TenantUserCreateIn,
    request: Request,
    session: TenantSchemaSession,
    _user: CurrentAdmin,
) -> TenantUserCreateOut:
    redis = getattr(request.app.state, "redis", None)
    svc = TenantUsersAdminService(session, redis=redis)
    try:
        user, token = await svc.create_user(
            email=str(body.email),
            full_name=body.full_name,
            is_admin=body.is_admin,
        )
    except TenantUserConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return TenantUserCreateOut(
        user=TenantUserOut.model_validate(user),
        password_reset_token=token,
        password_reset_expires_in=TenantUsersAdminService.admin_reset_ttl_seconds(),
    )


@router.get("/{user_id}", response_model=TenantUserOut)
async def get_tenant_user(
    tenant_id: uuid.UUID,  # noqa: ARG001
    user_id: uuid.UUID,
    session: TenantSchemaSession,
    _user: CurrentAdmin,
) -> TenantUserOut:
    user = await TenantUsersAdminService(session).get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Tenant user not found")
    return TenantUserOut.model_validate(user)


@router.patch("/{user_id}", response_model=TenantUserOut)
async def patch_tenant_user(
    tenant_id: uuid.UUID,  # noqa: ARG001
    user_id: uuid.UUID,
    body: TenantUserPatchIn,
    session: TenantSchemaSession,
    _user: CurrentAdmin,
) -> TenantUserOut:
    svc = TenantUsersAdminService(session)
    try:
        user = await svc.update_user(
            user_id=user_id,
            full_name=body.full_name,
            is_active=body.is_active,
            is_admin=body.is_admin,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TenantUserOut.model_validate(user)


@router.post("/{user_id}/password-reset", response_model=PasswordResetOut)
async def initiate_password_reset(
    tenant_id: uuid.UUID,  # noqa: ARG001
    user_id: uuid.UUID,
    request: Request,
    session: TenantSchemaSession,
    _user: CurrentAdmin,
) -> PasswordResetOut:
    redis = getattr(request.app.state, "redis", None)
    svc = TenantUsersAdminService(session, redis=redis)
    try:
        user, token = await svc.initiate_password_reset(user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PasswordResetOut(
        user_id=user.id,
        password_reset_token=token,
        password_reset_expires_in=TenantUsersAdminService.admin_reset_ttl_seconds(),
    )
