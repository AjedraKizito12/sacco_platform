import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.iam.passwords.service import verify_password
from app.platform_.models import PlatformUser
from scripts.seed_platform_admin import seed_platform_admin


@pytest.mark.asyncio
async def test_seed_creates_login_capable_superuser(test_engine):
    email = f"seed-{uuid.uuid4().hex[:8]}@platform.example.com"
    Session = async_sessionmaker(test_engine, expire_on_commit=False)
    async with Session() as s:
        user = await seed_platform_admin(
            s, email=email, full_name="Seed Admin", password="S33d-Password!"
        )
        await s.commit()
        assert user.role == "superuser"
        assert user.is_superuser is True
        assert user.hashed_password is not None
        assert verify_password("S33d-Password!", user.hashed_password)

    # Idempotent: second call updates password in place, no duplicate row.
    async with Session() as s:
        await seed_platform_admin(
            s, email=email, full_name="Seed Admin", password="New-Password!"
        )
        await s.commit()
    async with Session() as s:
        rows = (
            await s.execute(select(PlatformUser).where(PlatformUser.email == email))
        ).scalars().all()
        assert len(rows) == 1
        assert verify_password("New-Password!", rows[0].hashed_password)

    # cleanup
    async with Session() as s:
        await s.execute(
            PlatformUser.__table__.delete().where(PlatformUser.email == email)
        )
        await s.commit()
