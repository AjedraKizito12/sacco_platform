"""FastAPI router for /platform/users."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_platform_session
from app.modules.maker_checker.registry import approval_executor
from app.platform_.auth import CurrentSuperuser, CurrentSupport
from app.platform_.models import PlatformUser
from app.platform_.users.schemas import (
    CreatePlatformUserRequest,
    PlatformUserOut,
    UpdatePlatformUserRequest,
)
from app.platform_.users.service import MAKER_CHECKER_FIELDS, PlatformUserService

router = APIRouter(prefix="/platform/users", tags=["platform-users"])

Session = Annotated[AsyncSession, Depends(get_platform_session)]


@approval_executor("platform_user.update_sensitive")  # type: ignore[misc]
async def _execute_update_sensitive(session: AsyncSession, payload: dict) -> dict:  # type: ignore[type-arg]
    svc = PlatformUserService(session)
    user = await svc.update(
        uuid.UUID(payload["user_id"]),
        is_active=payload.get("is_active"),
        is_superuser=payload.get("is_superuser"),
        role=payload.get("role"),
    )
    return {"updated": str(user.id)}


@router.get("", response_model=list[PlatformUserOut])
async def list_users(session: Session, actor: CurrentSupport) -> list[PlatformUserOut]:
    svc = PlatformUserService(session)
    users = await svc.list_users()
    return [PlatformUserOut.model_validate(u) for u in users]


@router.get("/{user_id}", response_model=PlatformUserOut)
async def get_user(
    user_id: uuid.UUID,
    session: Session,
    actor: CurrentSupport,
) -> PlatformUserOut:
    svc = PlatformUserService(session)
    user = await svc.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Platform user not found")
    return PlatformUserOut.model_validate(user)


@router.post("", response_model=PlatformUserOut, status_code=201)
async def create_user(
    body: CreatePlatformUserRequest,
    session: Session,
    actor: CurrentSuperuser,
) -> PlatformUserOut:
    """Create a new platform user. Superuser only."""
    svc = PlatformUserService(session)
    try:
        user = await svc.create(
            email=str(body.email),
            full_name=body.full_name,
            role=body.role,
            is_superuser=body.is_superuser if body.is_superuser else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return PlatformUserOut.model_validate(user)


@router.patch("/{user_id}", response_model=PlatformUserOut)
async def update_user(
    user_id: uuid.UUID,
    body: UpdatePlatformUserRequest,
    session: Session,
    actor: CurrentSuperuser,
) -> PlatformUserOut:
    """Update a platform user.

    Changes to is_active or is_superuser go through maker-checker approval.
    Changes to full_name only are applied immediately.
    """
    from app.modules.maker_checker.service import ApprovalService

    sensitive_fields = {f for f in MAKER_CHECKER_FIELDS if getattr(body, f) is not None}
    svc = PlatformUserService(session)

    if sensitive_fields:
        approval_svc = ApprovalService(session)
        await approval_svc.submit(
            operation_type="platform_user.update_sensitive",
            payload={
                "user_id": str(user_id),
                "is_active": body.is_active,
                "is_superuser": body.is_superuser,
                "role": body.role,
            },
            requested_by=actor.id,
        )
        # Apply non-sensitive changes immediately if any.
        if body.full_name is not None:
            try:
                await svc.update(user_id, full_name=body.full_name)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        await session.commit()
        user = await svc.get(user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Platform user not found")
        return PlatformUserOut.model_validate(user)

    # Non-sensitive update (full_name only).
    try:
        user = await svc.update(user_id, full_name=body.full_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return PlatformUserOut.model_validate(user)
