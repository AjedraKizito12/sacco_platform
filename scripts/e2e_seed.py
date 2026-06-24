#!/usr/bin/env python3
"""Idempotent seed for portal e2e tests.

Creates the minimum a browser login + the smoke screens need:
  1. an active RS256 signing key for ``aud="platform"`` (JWT mode needs one);
  2. a login-capable platform superuser (argon2 password);
  3. one active ``platform.tenants`` row (display only — no provisioning).

Usage (from the project root, with the dev DB + JWT_KEK in env):

    DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5432/sacco \\
    JWT_KEK=<base64-32-bytes> python scripts/e2e_seed.py

Safe to run repeatedly — every step is a no-op when the row already exists.
"""
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Importing the billing models registers platform.subscriptions, which the
# tenants.current_subscription_id foreign key resolves against at mapper config.
import app.platform_.billing.models  # noqa: F401, E402
from app.core.config import get_settings
from app.modules.iam.keys.models import JwtSigningKey  # noqa: E402
from app.modules.iam.keys.service import KeyService  # noqa: E402
from app.modules.iam.passwords.service import hash_password  # noqa: E402
from app.platform_.models import PlatformUser, Tenant  # noqa: E402

E2E_EMAIL = os.environ.get("E2E_EMAIL", "e2e@platform.example.com")
E2E_PASSWORD = os.environ.get("E2E_PASSWORD", "e2e-Password-123!")
E2E_TENANT_SLUG = "e2e-sacco"
E2E_TENANT_SCHEMA = "tenant_e2e_sacco"
E2E_TENANT_NAME = "E2E SACCO"


async def _seed() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            await session.execute(text("SET search_path TO platform"))
            # AuditableMixin reads this to target platform.audit_log (no
            # impersonation_id column) rather than a tenant audit table.
            session.sync_session.info["is_platform"] = True

            # 1. Signing keys — one active key per audience (boot check needs
            #    both 'platform' and 'tenant' in jwt mode).
            for audience in ("platform", "tenant"):
                active_key = await session.scalar(
                    select(JwtSigningKey).where(
                        JwtSigningKey.audience == audience,
                        JwtSigningKey.status == "active",
                    )
                )
                if active_key is None:
                    await KeyService(session).generate_and_insert(audience)
                    print(f"seed: created {audience} signing key")
                else:
                    print(f"seed: {audience} signing key already present")

            # 2. Login-capable superuser.
            user = await session.scalar(
                select(PlatformUser).where(PlatformUser.email == E2E_EMAIL)
            )
            if user is None:
                session.add(
                    PlatformUser(
                        email=E2E_EMAIL,
                        full_name="E2E Operator",
                        hashed_password=hash_password(E2E_PASSWORD),
                        is_active=True,
                        is_superuser=True,
                        role="superuser",
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )
                )
                print(f"seed: created superuser {E2E_EMAIL}")
            else:
                print(f"seed: superuser {E2E_EMAIL} already present")

            # 3. One active tenant row (display only — no async provisioning).
            tenant = await session.scalar(
                select(Tenant).where(Tenant.slug == E2E_TENANT_SLUG)
            )
            if tenant is None:
                session.add(
                    Tenant(
                        slug=E2E_TENANT_SLUG,
                        schema_name=E2E_TENANT_SCHEMA,
                        name=E2E_TENANT_NAME,
                        status="active",
                        is_active=True,
                        subscription_status="active",
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )
                )
                print(f"seed: created tenant {E2E_TENANT_SLUG}")
            else:
                print(f"seed: tenant {E2E_TENANT_SLUG} already present")

            await session.commit()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_seed())
