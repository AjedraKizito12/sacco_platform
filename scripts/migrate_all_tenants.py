#!/usr/bin/env python3
"""Run Alembic tenant migrations for every active tenant in platform.tenants.

Usage (from project root):
    DATABASE_URL=postgresql+asyncpg://... python scripts/migrate_all_tenants.py

Exits 0 if all tenants migrated successfully, 1 if any failed.
"""
import os
import re
import subprocess
import sys

import psycopg2  # type: ignore[import-untyped]

_DATABASE_URL = os.environ["DATABASE_URL"]
# psycopg2 needs a plain postgresql:// URL.
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
        print(f"[SKIP] {schema_name!r} — invalid schema name, skipping", file=sys.stderr)
        return False

    result = subprocess.run(  # noqa: S603
        ["alembic", "-c", "alembic-tenant.ini", "upgrade", "head"],  # noqa: S607
        env={**os.environ, "TENANT_SCHEMA": schema_name},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[FAIL] {schema_name}\n{result.stderr}", file=sys.stderr)
        return False

    print(f"[OK]   {schema_name}")
    return True


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
