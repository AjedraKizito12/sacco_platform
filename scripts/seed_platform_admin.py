"""Create (or reset) a login-capable platform superuser.

PlatformUserService.create intentionally leaves hashed_password NULL, so the
bootstrap admin cannot log into the portal. This seed sets a password directly,
mirroring scripts/e2e_seed.py, and is idempotent by email.

Usage (on the server, inside the api image):
    python scripts/seed_platform_admin.py --email admin@you.tld --full-name "Ops Admin"
The password is read from SEED_ADMIN_PASSWORD or prompted interactively.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime
from getpass import getpass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.modules.iam.passwords.service import hash_password
from app.platform_.models import PlatformUser


async def seed_platform_admin(
    session: AsyncSession,
    *,
    email: str,
    full_name: str,
    password: str,
    role: str = "superuser",
) -> PlatformUser:
    """Idempotently ensure a platform user with the given email exists, has the
    given role, and can log in with the given password. Returns the user."""
    existing = (
        await session.execute(select(PlatformUser).where(PlatformUser.email == email))
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    if existing is None:
        user = PlatformUser(
            email=email,
            full_name=full_name,
            role=role,
            is_superuser=(role == "superuser"),
            is_active=True,
            hashed_password=hash_password(password),
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        await session.flush()
        return user

    existing.full_name = full_name
    existing.role = role
    existing.is_superuser = role == "superuser"
    existing.hashed_password = hash_password(password)
    existing.is_active = True
    existing.updated_at = now
    await session.flush()
    return existing


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Seed a platform superuser")
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", default="Platform Admin")
    parser.add_argument("--role", default="superuser")
    args = parser.parse_args()

    password = os.environ.get("SEED_ADMIN_PASSWORD") or getpass("Password: ")
    if len(password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        return 2

    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        user = await seed_platform_admin(
            session,
            email=args.email,
            full_name=args.full_name,
            password=password,
            role=args.role,
        )
        await session.commit()
        print(f"Seeded platform user {user.email} (role={user.role}).")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
