"""Lifecycle management for platform-user → tenant impersonation sessions.

The service handles the *request*, *end*, *revoke*, and *queries* paths.
The *create-on-approval* path runs inside the maker-checker executor
(see executors.py), so callers never insert support_impersonations rows
directly.

All methods operate against a platform-scoped session (the caller is
responsible for SET LOCAL search_path TO platform + setting
session.sync_session.info["is_platform"]=True; the standard
get_platform_session dependency does both).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy import text as sql_text

from app.core import db as _core_db  # accessed at call time for testability
from app.core.config import get_settings
from app.modules.iam.keys.service import KeyService
from app.modules.iam.sessions.models import TenantSession
from app.modules.iam.sessions.service import SessionService
from app.modules.iam.tenant_users.models import TenantUser
from app.modules.iam.tokens.service import (
    encode_access_token,
    encode_refresh_token,
)
from app.modules.maker_checker.models.platform import PlatformApprovalRequest
from app.modules.maker_checker.service import ApprovalService
from app.platform_.impersonations.exceptions import ImpersonationGone
from app.platform_.impersonations.models import SupportImpersonation
from app.platform_.impersonations.schemas import MintTenantTokenOut
from app.platform_.models import PlatformUser, Tenant

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class ImpersonationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def request(
        self,
        *,
        platform_user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        reason: str,
    ) -> PlatformApprovalRequest:
        """Submit an ApprovalRequest for a new impersonation session.

        Returns the pending approval request; the impersonation row is
        created later by the executor when the checker approves.

        Raises:
            ValueError: if reason is too short, tenant unknown/inactive,
                or platform_user_id has no matching active user.
        """
        if len(reason.strip()) < 10:
            raise ValueError("reason must be at least 10 characters")

        tenant = await self._session.get(Tenant, tenant_id)
        if tenant is None or not tenant.is_active:
            raise ValueError(f"Tenant {tenant_id} not found or inactive")

        settings = get_settings()
        approval = await ApprovalService(self._session).submit(
            operation_type="platform.start_impersonation",
            payload={
                "platform_user_id": str(platform_user_id),
                "tenant_id": str(tenant_id),
                "reason": reason,
            },
            requested_by=platform_user_id,
            required_approvals=settings.impersonation_default_required_approvals,
        )
        return approval  # type: ignore[return-value]

    async def get_by_id(
        self, impersonation_id: uuid.UUID
    ) -> SupportImpersonation | None:
        return await self._session.get(SupportImpersonation, impersonation_id)

    async def get_active_for_user(
        self, *, platform_user_id: uuid.UUID
    ) -> list[SupportImpersonation]:
        """Return non-ended, non-revoked, non-expired impersonations for a user."""
        now = datetime.now(UTC)
        q = (
            select(SupportImpersonation)
            .where(
                SupportImpersonation.platform_user_id == platform_user_id,
                SupportImpersonation.ended_at.is_(None),
                SupportImpersonation.revoked_at.is_(None),
                SupportImpersonation.expires_at > now,
            )
            .order_by(SupportImpersonation.started_at.desc())
        )
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def get_all_active(self) -> list[SupportImpersonation]:
        """Return ALL non-ended, non-revoked, non-expired impersonations."""
        now = datetime.now(UTC)
        q = (
            select(SupportImpersonation)
            .where(
                SupportImpersonation.ended_at.is_(None),
                SupportImpersonation.revoked_at.is_(None),
                SupportImpersonation.expires_at > now,
            )
            .order_by(SupportImpersonation.started_at.desc())
        )
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def is_active(self, impersonation_id: uuid.UUID) -> bool:
        """True iff the row exists, is not ended, not revoked, not expired."""
        row = await self.get_by_id(impersonation_id)
        if row is None:
            return False
        if row.ended_at is not None or row.revoked_at is not None:
            return False
        return row.expires_at > datetime.now(UTC)

    async def end(
        self,
        *,
        impersonation_id: uuid.UUID,
        ended_by: uuid.UUID,
    ) -> SupportImpersonation:
        """Mark an impersonation as ended by its owner.

        Deactivates the shadow tenant_user (if minted) and revokes all its
        tenant sessions in the same cross-schema transaction.

        Idempotent: re-calling end() on an already-ended row is a no-op.
        """
        row = await self._session.get(SupportImpersonation, impersonation_id)
        if row is None:
            raise ValueError(f"Impersonation {impersonation_id} not found")
        if row.ended_at is not None or row.revoked_at is not None:
            return row
        row.ended_at = datetime.now(UTC)
        row.ended_by = ended_by
        await self._deactivate_shadow_and_revoke_sessions(row)
        return row

    async def revoke(
        self,
        *,
        impersonation_id: uuid.UUID,
        revoked_by: uuid.UUID,
    ) -> SupportImpersonation:
        """Forcibly revoke an impersonation (admin action).

        Caller must verify revoked_by has the authority. 02b's API gates
        this on a role check via P1.7-05.

        Deactivates the shadow tenant_user (if minted) and revokes all its
        tenant sessions in the same cross-schema transaction.

        Idempotent: re-calling revoke() on an already-revoked row is a no-op.
        """
        row = await self._session.get(SupportImpersonation, impersonation_id)
        if row is None:
            raise ValueError(f"Impersonation {impersonation_id} not found")
        if row.revoked_at is not None or row.ended_at is not None:
            return row
        row.revoked_at = datetime.now(UTC)
        row.revoked_by = revoked_by
        await self._deactivate_shadow_and_revoke_sessions(row)
        return row

    async def mint_tenant_token(
        self,
        *,
        impersonation_id: uuid.UUID,
        user_agent: str | None,
        ip_address: str | None,
        redis: Any | None = None,
    ) -> MintTenantTokenOut:
        """Mint a tenant access+refresh token pair for an active impersonation.

        Side effects:
        - Lazily creates the shadow tenant_user on first call (idempotent).
        - Creates a tenant_sessions row + Redis JTI key.
        - Updates support_impersonations.tenant_user_id on first call.

        Raises:
            ValueError: impersonation not found
            ImpersonationGone: ended, revoked, or expired
        """
        imp = await self._session.get(SupportImpersonation, impersonation_id)
        if imp is None:
            raise ValueError(f"Impersonation {impersonation_id} not found")
        if imp.ended_at is not None or imp.revoked_at is not None:
            raise ImpersonationGone("Impersonation has ended or been revoked")
        if imp.expires_at <= datetime.now(UTC):
            raise ImpersonationGone("Impersonation has expired")

        tenant = await self._session.get(Tenant, imp.tenant_id)
        if tenant is None or not tenant.is_active:
            raise ValueError(f"Tenant {imp.tenant_id} unavailable")

        platform_user = await self._session.get(PlatformUser, imp.platform_user_id)
        if platform_user is None:
            raise ValueError(f"Platform user {imp.platform_user_id} not found")

        # Fetch signing material BEFORE opening the secondary session — the
        # KeyService reads from the platform schema and we already hold that.
        kid, private_key_pem, algorithm = await KeyService(
            self._session
        ).get_active_signing_key("tenant")

        settings = get_settings()
        audience = f"tenant:{tenant.slug}"

        # Cross-schema work: a new session bound to the tenant's schema.
        # Validation of schema_name was performed when the tenant was created.
        shadow_id: uuid.UUID
        access_token: str
        refresh_token: str
        async with _core_db.AsyncSessionFactory() as tenant_db:
            await tenant_db.execute(
                sql_text(
                    f"SET LOCAL search_path TO {tenant.schema_name}, platform"
                )
            )

            # Look up or create shadow tenant_user.
            shadow = await tenant_db.scalar(
                select(TenantUser).where(
                    TenantUser.impersonation_id == impersonation_id
                )
            )
            if shadow is None:
                shadow = TenantUser(
                    email=f"imp.{impersonation_id.hex[:12]}@platform.local",
                    full_name=(
                        f"{platform_user.full_name} "
                        f"(Platform Admin Impersonation)"
                    ),
                    is_active=True,
                    is_admin=True,
                    hashed_password=None,
                    impersonation_id=impersonation_id,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                tenant_db.add(shadow)
                await tenant_db.flush()
            elif not shadow.is_active:
                shadow.is_active = True
            shadow_id = shadow.id

            # Create the tenant session row.
            jti = str(uuid.uuid4())
            sess_row = await SessionService(
                db=tenant_db, model_cls=TenantSession, redis=redis
            ).create(
                user_id=shadow.id,
                jti=jti,
                user_agent=user_agent,
                ip_address=ip_address,
                refresh_ttl_seconds=settings.jwt_refresh_ttl_tenant_seconds,
            )
            await tenant_db.flush()

            access_token = encode_access_token(
                sub=str(shadow.id),
                audience=audience,
                session_id=str(sess_row.id),
                actor_type="tenant_user",
                kid=kid,
                private_key_pem=private_key_pem,
                algorithm=algorithm,
                ttl_seconds=settings.jwt_access_ttl_seconds,
            )
            refresh_token = encode_refresh_token(
                sub=str(shadow.id),
                audience=audience,
                session_id=str(sess_row.id),
                jti=jti,
                kid=kid,
                private_key_pem=private_key_pem,
                algorithm=algorithm,
                ttl_seconds=settings.jwt_refresh_ttl_tenant_seconds,
            )
            await tenant_db.commit()

        # Back in the platform session: link the shadow into the impersonation row.
        if imp.tenant_user_id is None:
            imp.tenant_user_id = shadow_id

        return MintTenantTokenOut(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_ttl_seconds,
            tenant_slug=tenant.slug,
            impersonation_id=impersonation_id,
            impersonation_expires_at=imp.expires_at,
        )

    async def _deactivate_shadow_and_revoke_sessions(
        self, row: SupportImpersonation
    ) -> None:
        """Flip the shadow tenant_user inactive and revoke its tenant sessions.

        Runs in a secondary tenant-scoped session for cross-schema work.
        No-op if no shadow user has been minted yet (tenant_user_id IS NULL).
        """
        if row.tenant_user_id is None:
            return

        tenant = await self._session.get(Tenant, row.tenant_id)
        if tenant is None:
            return  # tenant gone; nothing to clean up

        async with _core_db.AsyncSessionFactory() as tenant_db:
            await tenant_db.execute(
                sql_text(
                    f"SET LOCAL search_path TO {tenant.schema_name}, platform"
                )
            )
            shadow = await tenant_db.get(TenantUser, row.tenant_user_id)
            if shadow is not None and shadow.is_active:
                shadow.is_active = False
                shadow.updated_at = datetime.now(UTC)
            # Revoke every session belonging to the shadow user.
            await SessionService(
                db=tenant_db, model_cls=TenantSession, redis=None
            ).revoke_all_for_user(row.tenant_user_id)
            await tenant_db.commit()

    @staticmethod
    def compute_expires_at(*, started_at: datetime | None = None) -> datetime:
        """Compute expires_at from settings.impersonation_max_minutes.

        Pure helper exposed so the executor and any future re-mint code
        can stay in sync.
        """
        settings = get_settings()
        anchor = started_at or datetime.now(UTC)
        return anchor + timedelta(minutes=settings.impersonation_max_minutes)
