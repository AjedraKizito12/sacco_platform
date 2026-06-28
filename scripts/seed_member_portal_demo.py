#!/usr/bin/env python3
"""Idempotent demo seed for manually testing the member self-service portal.

Targets the existing ``tenant_sacco_one`` schema. Steps (all idempotent):

  1. Register a ``platform.tenants`` row (slug ``sacco-one``) so slug→schema
     resolution works for operator + member logins.
  2. Run tenant Alembic migrations to head (brings in the member-auth columns
     + ``member_sessions`` from migration 015).
  3. Seed tenant defaults (chart of accounts, fee types, roles, templates).
  4. Seed the rich "Demo Member" data set (savings + loan + fees) via the
     existing smoke seed.
  5. Seed two additional members each with a savings account + deposits.
  6. Create a login-capable operator (``tenant_users``) account.
  7. Enable member-portal access (password + portal_enabled + active + email)
     for all three demo members.

Usage (from project root, with the dev DB env loaded):

    set -a && . ./.env && set +a && venv/bin/python scripts/seed_member_portal_demo.py

Re-running is safe — every step is a no-op when the row already exists.

Credentials it creates:
  Operator (operator portal, X-Tenant-Slug: sacco-one)
    ops@sacco-one.example.com / Operator!2026
  Members (member portal, X-Tenant-Slug: sacco-one)
    demo.member@example.com  / MemberPass!2026
    sarah.nakato@example.com / MemberPass!2026
    david.okello@example.com / MemberPass!2026
"""
from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Importing billing models registers platform.subscriptions, which the
# tenants.current_subscription_id FK resolves against at mapper config.
import app.platform_.billing.models  # noqa: F401
from app.core.config import get_settings
from app.modules.iam.passwords.service import hash_password
from app.platform_.models import Tenant
from app.platform_.provisioning.migrations import run_tenant_migrations
from app.platform_.seeds.runner import seed_defaults
from app.platform_.seeds.smoke import (
    _SYSTEM,
    _id,
    _insert_journal_entry,
    _insert_journal_line,
    seed_smoke_data,
)

SLUG = "sacco-one"
SCHEMA = "tenant_sacco_one"
NAME = "Sacco One"

OPERATOR_EMAIL = "ops@sacco-one.example.com"
OPERATOR_PASSWORD = "Operator!2026"
MEMBER_PASSWORD = "MemberPass!2026"

# (member_number, full_name, dob, gender, email, phone, deposits)
EXTRA_MEMBERS: list[tuple[str, str, date, str, str, str, list[tuple[Decimal, date, str]]]] = [
    (
        "M-1001",
        "Sarah Nakato",
        date(1988, 3, 12),
        "female",
        "sarah.nakato@example.com",
        "+256700111222",
        [
            (Decimal("1000"), date(2026, 1, 8), "Opening deposit"),
            (Decimal("500"), date(2026, 1, 20), "Top-up deposit"),
        ],
    ),
    (
        "M-1002",
        "David Okello",
        date(1992, 7, 5),
        "male",
        "david.okello@example.com",
        "+256700333444",
        [
            (Decimal("800"), date(2026, 1, 15), "Opening deposit"),
        ],
    ),
]

# Members that get member-portal access: (member_id, email).
PORTAL_MEMBERS = [
    (_id(SCHEMA, "member"), "demo.member@example.com"),  # the smoke "Demo Member"
]


async def _register_tenant(engine) -> None:  # noqa: ANN001
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text("SET search_path TO platform"))
        session.sync_session.info["is_platform"] = True
        existing = await session.scalar(select(Tenant).where(Tenant.slug == SLUG))
        if existing is None:
            session.add(
                Tenant(
                    slug=SLUG,
                    schema_name=SCHEMA,
                    name=NAME,
                    status="active",
                    is_active=True,
                    subscription_status="active",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
            print(f"seed: registered tenant {SLUG} -> {SCHEMA}")
        else:
            print(f"seed: tenant {SLUG} already present")
        await session.commit()


async def _resolve_coa(session) -> dict[str, str]:  # noqa: ANN001
    rows = (
        await session.execute(
            text("SELECT code, id::text FROM chart_of_accounts WHERE code IN ('1000','2000')")
        )
    ).all()
    return {code: id_ for code, id_ in rows}


async def _seed_extra_members(engine) -> None:  # noqa: ANN001
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await session.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))  # noqa: S608
        coa = await _resolve_coa(session)
        # Reuse the smoke "Demo Savings" product so we don't create duplicates.
        sp_id = _id(SCHEMA, "savings_product")

        for member_number, full_name, dob, gender, email, phone, deposits in EXTRA_MEMBERS:
            member_id = _id(SCHEMA, f"member_{member_number}")
            await session.execute(
                text(
                    "INSERT INTO members "
                    "(id, member_number, full_name, date_of_birth, gender, phone, email, "
                    "status, joined_at, created_at, updated_at) "
                    "VALUES (CAST(:id AS uuid), :num, :name, :dob, :gender, :phone, :email, "
                    "'active', '2026-01-01', now(), now()) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": member_id,
                    "num": member_number,
                    "name": full_name,
                    "dob": dob,
                    "gender": gender,
                    "phone": phone,
                    "email": email,
                },
            )
            sa_id = _id(SCHEMA, f"sa_{member_number}")
            await session.execute(
                text(
                    "INSERT INTO savings_accounts "
                    "(id, member_id, savings_product_id, product_name, interest_rate, "
                    "minimum_balance, liability_account_id, created_at, updated_at) "
                    "VALUES (CAST(:id AS uuid), CAST(:mid AS uuid), CAST(:spid AS uuid), "
                    "'Demo Savings', 5.0000, 0, CAST(:liab AS uuid), now(), now()) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"id": sa_id, "mid": member_id, "spid": sp_id, "liab": coa["2000"]},
            )
            for i, (amount, when, narration) in enumerate(deposits, start=1):
                je_id = _id(SCHEMA, f"je_sav_{member_number}_{i}")
                tx_id = _id(SCHEMA, f"sav_txn_{member_number}_{i}")
                posted_at = datetime(when.year, when.month, when.day, 10, 0, tzinfo=UTC)
                await _insert_journal_entry(
                    session,
                    je_id=je_id,
                    reference=f"DEMO-SAV-{member_number}-{i:03d}",
                    description=narration,
                    posted_at=posted_at,
                )
                # Deposit: dr cash (1000), cr savings liability (2000)
                await _insert_journal_line(
                    session, _id(SCHEMA, f"jl_{member_number}_{i}_dr"), je_id,
                    coa["1000"], amount, Decimal("0"),
                )
                await _insert_journal_line(
                    session, _id(SCHEMA, f"jl_{member_number}_{i}_cr"), je_id,
                    coa["2000"], Decimal("0"), amount,
                )
                await session.execute(
                    text(
                        "INSERT INTO savings_transactions "
                        "(id, savings_account_id, transaction_type, amount, narration, "
                        "journal_entry_id, posted_by, posted_at, idempotency_key) "
                        "VALUES (CAST(:id AS uuid), CAST(:sa AS uuid), 'deposit', :amt, :narr, "
                        "CAST(:je AS uuid), CAST(:by AS uuid), :at, :idem) "
                        "ON CONFLICT (id) DO NOTHING"
                    ),
                    {
                        "id": tx_id, "sa": sa_id, "amt": amount, "narr": narration,
                        "je": je_id, "by": str(_SYSTEM), "at": posted_at,
                        "idem": _id(SCHEMA, f"sav_idem_{member_number}_{i}"),
                    },
                )
            print(f"seed: member {member_number} ({full_name}) + savings")
            PORTAL_MEMBERS.append((member_id, email))


async def _seed_operator(engine) -> None:  # noqa: ANN001
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await session.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))  # noqa: S608
        await session.execute(
            text(
                "INSERT INTO tenant_users "
                "(id, email, full_name, hashed_password, is_active, is_admin, "
                "created_at, updated_at) "
                "VALUES (gen_random_uuid(), :email, 'Operations Admin', :pw, true, true, "
                "now(), now()) "
                "ON CONFLICT (email) DO UPDATE SET hashed_password = EXCLUDED.hashed_password, "
                "is_active = true, is_admin = true, updated_at = now()"
            ),
            {"email": OPERATOR_EMAIL, "pw": hash_password(OPERATOR_PASSWORD)},
        )
        print(f"seed: operator {OPERATOR_EMAIL}")


async def _enable_member_portal(engine) -> None:  # noqa: ANN001
    pw = hash_password(MEMBER_PASSWORD)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await session.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))  # noqa: S608
        for member_id, email in PORTAL_MEMBERS:
            await session.execute(
                text(
                    "UPDATE members SET hashed_password = :pw, portal_enabled = true, "
                    "status = 'active', "
                    "email = COALESCE(NULLIF(email, ''), :email), updated_at = now() "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {"pw": pw, "email": email, "id": member_id},
            )
            print(f"seed: member portal enabled for {email}")


async def _main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        await _register_tenant(engine)
        # Tenant DDL to head (member-auth cols + member_sessions). Sync call.
        run_tenant_migrations(SCHEMA)
        print(f"seed: {SCHEMA} migrated to head")
        await seed_defaults(engine, SCHEMA)
        print(f"seed: defaults (COA, fee types, roles, templates) into {SCHEMA}")
        await seed_smoke_data(engine, SCHEMA)
        print(f"seed: smoke data (Demo Member + savings/loan/fees) into {SCHEMA}")
        await _seed_extra_members(engine)
        await _seed_operator(engine)
        await _enable_member_portal(engine)
    finally:
        await engine.dispose()
    print("\nseed complete. Credentials:")
    print(f"  operator  {OPERATOR_EMAIL} / {OPERATOR_PASSWORD}  (X-Tenant-Slug: {SLUG})")
    for _, email in PORTAL_MEMBERS:
        print(f"  member    {email} / {MEMBER_PASSWORD}  (X-Tenant-Slug: {SLUG})")


if __name__ == "__main__":
    asyncio.run(_main())
