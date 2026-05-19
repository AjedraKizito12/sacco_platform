#!/usr/bin/env python3
"""Run Alembic tenant migrations for every active tenant in platform.tenants.

Usage (from project root):
    DATABASE_URL=postgresql+asyncpg://... python scripts/migrate_all_tenants.py

Exits 0 if all tenants migrated successfully, 1 if any failed.
"""
import os
import re
import sys

import psycopg2  # type: ignore[import-untyped]

from app.platform_.provisioning.migrations import run_tenant_migrations

_DATABASE_URL = os.environ["DATABASE_URL"]
_SYNC_URL = re.sub(r"^postgresql\+asyncpg", "postgresql", _DATABASE_URL)

_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")


def _get_tenant_schemas() -> list[str]:
    conn = psycopg2.connect(_SYNC_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT schema_name FROM platform.tenants"
                " WHERE is_active = true ORDER BY schema_name"
            )
            rows: list[tuple[str]] = cur.fetchall()
    finally:
        conn.close()
    return [row[0] for row in rows]


def _migrate_tenant(schema_name: str) -> bool:
    if not _SCHEMA_RE.match(schema_name):
        print(f"[SKIP] {schema_name!r} — invalid schema name", file=sys.stderr)
        return False
    try:
        run_tenant_migrations(schema_name)
        print(f"[OK]   {schema_name}")
        return True
    except Exception as exc:
        print(f"[FAIL] {schema_name}\n{exc}", file=sys.stderr)
        return False


def main() -> None:
    schemas = _get_tenant_schemas()
    print(f"Found {len(schemas)} active tenant(s)")
    failed = [s for s in schemas if not _migrate_tenant(s)]
    if failed:
        print(f"\nFailed tenants: {failed}", file=sys.stderr)
        sys.exit(1)
    print(f"\nAll {len(schemas)} tenant(s) migrated successfully.")


if __name__ == "__main__":
    main()
