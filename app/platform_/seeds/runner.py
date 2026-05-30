"""Seed runner: inserts default data into a newly provisioned tenant schema.

Each entity type is attempted independently. Missing tables (from modules not
yet shipped) are caught as ``sqlalchemy.exc.ProgrammingError`` and skipped
with a warning. This makes the seed step safe to run at any point in the
module rollout.

seed_version=1 is the initial seed. Future modules increment this and check
before applying their entities.
"""
from __future__ import annotations

import uuid

import structlog
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.platform_.seeds.chart_of_accounts import CHART_OF_ACCOUNTS
from app.platform_.seeds.defaults import (
    DEFAULT_FEE_TYPES,
    DEFAULT_PRODUCT_TEMPLATES,
    DEFAULT_ROLES,
)

_log = structlog.get_logger(__name__)


async def seed_defaults(
    engine: AsyncEngine,
    schema_name: str,
    admin_email: str | None = None,
) -> None:
    """Seed all default data into *schema_name*.

    Skips entity types whose tables don't exist yet.
    Called by the provisioning task after run_migrations step.

    Args:
        admin_email: If provided, inserts an admin tenant user with this email
            (hashed_password=null). The user activates via the password reset
            flow (Plan 08). Idempotent — safe to call multiple times.
    """
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session, session.begin():
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )
        await _seed_roles(session, schema_name)
        await _seed_fee_types(session, schema_name)
        await _seed_chart_of_accounts(session, schema_name)
        await _seed_product_templates(session, schema_name)
        if admin_email:
            await _seed_admin_user(session, schema_name, admin_email)


async def _seed_roles(session: AsyncSession, schema_name: str) -> None:
    for role in DEFAULT_ROLES:
        try:
            async with session.begin_nested():
                await session.execute(
                    text(
                        "INSERT INTO roles (name, description, created_at, updated_at) "
                        "VALUES (:name, :description, now(), now()) "
                        "ON CONFLICT (name) DO NOTHING"
                    ),
                    {"name": role["name"], "description": role["description"]},
                )
        except ProgrammingError:
            _log.warning("seed.roles_table_missing", schema=schema_name)
            return


async def _seed_fee_types(session: AsyncSession, schema_name: str) -> None:
    import json
    for ft in DEFAULT_FEE_TYPES:
        try:
            async with session.begin_nested():
                await session.execute(
                    text(
                        "INSERT INTO fee_types "
                        "(id, code, name, description, applicable_to, amount_kind, amount, currency, "
                        "trigger_kind, event_name, schedule_config, "
                        "gl_income_account_code, gl_receivable_account_code, "
                        "is_active, requires_collection, created_at, updated_at) "
                        "VALUES (:id, :code, :name, :description, :applicable_to, :amount_kind, "
                        ":amount, :currency, :trigger_kind, :event_name, "
                        "CAST(:schedule_config AS jsonb), "
                        ":gl_income_account_code, :gl_receivable_account_code, "
                        ":is_active, :requires_collection, now(), now()) "
                        "ON CONFLICT (code) DO NOTHING"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "code": ft["code"],
                        "name": ft["name"],
                        "description": ft.get("description"),
                        "applicable_to": ft["applicable_to"],
                        "amount_kind": ft["amount_kind"],
                        "amount": ft["amount"],
                        "currency": ft["currency"],
                        "trigger_kind": ft["trigger_kind"],
                        "event_name": ft.get("event_name"),
                        "schedule_config": json.dumps(ft["schedule_config"]) if ft.get("schedule_config") else None,
                        "gl_income_account_code": ft["gl_income_account_code"],
                        "gl_receivable_account_code": ft["gl_receivable_account_code"],
                        "is_active": ft["is_active"],
                        "requires_collection": ft["requires_collection"],
                    },
                )
        except ProgrammingError:
            _log.warning("seed.fee_types_table_missing", schema=schema_name)
            return


async def _seed_chart_of_accounts(session: AsyncSession, schema_name: str) -> None:
    for account in CHART_OF_ACCOUNTS:
        try:
            async with session.begin_nested():
                await session.execute(
                    text(
                        "INSERT INTO chart_of_accounts "
                        "(id, code, name, account_type, "
                        "is_active, created_at, updated_at) "
                        "VALUES (:id, :code, :name, :account_type, "
                        "true, now(), now()) "
                        "ON CONFLICT (code) DO NOTHING"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "code": account["code"],
                        "name": account["name"],
                        "account_type": account["account_type"],
                    },
                )
        except ProgrammingError:
            _log.warning("seed.chart_of_accounts_table_missing", schema=schema_name)
            return


async def _seed_product_templates(session: AsyncSession, schema_name: str) -> None:
    for pt in DEFAULT_PRODUCT_TEMPLATES:
        try:
            async with session.begin_nested():
                await session.execute(
                    text(
                        "INSERT INTO product_templates "
                        "(code, name, product_type, status, currency, "
                        "created_at, updated_at) "
                        "VALUES (:code, :name, :product_type, :status, "
                        ":currency, now(), now()) "
                        "ON CONFLICT (code) DO NOTHING"
                    ),
                    {
                        "code": pt["code"],
                        "name": pt["name"],
                        "product_type": pt["product_type"],
                        "status": pt["status"],
                        "currency": pt["currency"],
                    },
                )
        except ProgrammingError:
            _log.warning("seed.product_templates_table_missing", schema=schema_name)
            return


async def _seed_admin_user(
    session: AsyncSession, schema_name: str, email: str
) -> None:
    """Insert an admin tenant user if one does not already exist for this email."""
    try:
        async with session.begin_nested():
            await session.execute(
                text(
                    "INSERT INTO tenant_users "
                    "(id, email, full_name, is_active, is_admin, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :email, 'Admin', true, true, now(), now()) "
                    "ON CONFLICT (email) DO NOTHING"
                ),
                {"email": email},
            )
        _log.info(
            "seed.admin_user_seeded",
            schema=schema_name,
            email=email,
            note="hashed_password is null — user must set password via reset flow",
        )
    except ProgrammingError:
        _log.warning("seed.tenant_users_table_missing", schema=schema_name)
