"""Shared Alembic migration helper for tenant schemas.

Used by both the provisioning Celery task and scripts/migrate_all_tenants.py.
Programmatic invocation — no subprocess required.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from alembic import command
from alembic.config import Config

_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")

# Path to the tenant Alembic ini file (relative to this file's location).
_INI_PATH = Path(__file__).parent.parent.parent.parent / "alembic-tenant.ini"


def run_tenant_migrations(schema_name: str) -> None:
    """Run ``alembic upgrade head`` for *schema_name* using the programmatic API.

    Sets ``TENANT_SCHEMA`` in the environment for the duration of the call
    (thread-safe enough for single-threaded Celery workers with prefetch=1).
    Also passes the schema via ``config.attributes`` as the preferred path
    for the updated ``alembic/tenant/env.py``.

    Raises ``ValueError`` if *schema_name* fails validation.
    Raises ``alembic.util.exc.CommandError`` on migration failure.
    """
    if not _SCHEMA_RE.match(schema_name):
        raise ValueError(f"Invalid schema_name: {schema_name!r}")

    cfg = Config(str(_INI_PATH))
    cfg.attributes["tenant_schema"] = schema_name  # preferred path

    # Also set env var as fallback for any subprocess-based tooling.
    old = os.environ.get("TENANT_SCHEMA")
    try:
        os.environ["TENANT_SCHEMA"] = schema_name
        command.upgrade(cfg, "head")
    finally:
        if old is None:
            os.environ.pop("TENANT_SCHEMA", None)
        else:
            os.environ["TENANT_SCHEMA"] = old
