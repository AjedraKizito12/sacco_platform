"""Alembic env for per-tenant schemas.

TENANT_SCHEMA must be set in the environment before running this.
Hard-fails if it is absent or does not match ^tenant_[a-z0-9_]{1,40}$.

Usage:
    TENANT_SCHEMA=tenant_acme alembic -c alembic-tenant.ini upgrade head
"""
import os
import re
from logging.config import fileConfig
from pathlib import Path

# Load .env so DATABASE_URL is available when invoked from Celery or CLI.
_env_file = Path(__file__).parents[2] / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file, override=False)

from sqlalchemy import create_engine, pool, text

# Import Base so tenant model metadata is available.
# (Add `from app.modules.<name>.models import *` as tenant models are created.)
import app.core.audit.models  # noqa: F401 — registers audit tables in Base.metadata
import app.core.outbox.models  # noqa: F401 — registers outbox tables in Base.metadata
import app.modules.maker_checker.models  # noqa: F401 — registers maker-checker tables in Base.metadata
import app.modules.ledger.models  # noqa: F401 — registers ledger tables in Base.metadata
from alembic import context
from app.core.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_DATABASE_URL = os.environ["DATABASE_URL"]
_SYNC_URL = re.sub(r"^postgresql\+asyncpg", "postgresql+psycopg2", _DATABASE_URL)

# Support programmatic invocation via config.attributes["tenant_schema"]
# (preferred for the provisioning task) with fallback to env var (CLI usage).
_TENANT_SCHEMA = (
    context.config.attributes.get("tenant_schema")
    or os.environ.get("TENANT_SCHEMA", "")
).strip()

if not _TENANT_SCHEMA:
    raise RuntimeError(
        "TENANT_SCHEMA must be set — either via config.attributes['tenant_schema'] "
        "(programmatic) or the TENANT_SCHEMA environment variable (CLI). "
        "Example: TENANT_SCHEMA=tenant_acme alembic -c alembic-tenant.ini upgrade head"
    )

_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")
if not _SCHEMA_RE.match(_TENANT_SCHEMA):
    raise RuntimeError(
        f"TENANT_SCHEMA '{_TENANT_SCHEMA}' is invalid. "
        r"Must match ^tenant_[a-z0-9_]{1,40}$"
    )


def run_migrations_online() -> None:
    connectable = create_engine(
        _SYNC_URL,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=False,
            version_table="alembic_version",
        )
        with context.begin_transaction():
            # SET search_path inside the migration transaction — it's a session-level
            # statement so it persists for the connection, but running it here avoids
            # triggering SA 2.0 autobegin before begin_transaction(), which would
            # demote begin_transaction() to a SAVEPOINT that never commits.
            # _TENANT_SCHEMA is validated above — safe to interpolate.
            connection.execute(text(f"SET search_path TO {_TENANT_SCHEMA}"))  # noqa: S608
            context.run_migrations()


run_migrations_online()
