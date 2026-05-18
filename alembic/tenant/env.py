"""Alembic env for per-tenant schemas.

TENANT_SCHEMA must be set in the environment before running this.
Hard-fails if it is absent or does not match ^tenant_[a-z0-9_]{1,40}$.

Usage:
    TENANT_SCHEMA=tenant_acme alembic -c alembic-tenant.ini upgrade head
"""
import os
import re
from logging.config import fileConfig

from sqlalchemy import create_engine, pool, text

# Import Base so tenant model metadata is available.
# (Add `from app.modules.<name>.models import *` as tenant models are created.)
import app.core.audit.models  # noqa: F401 — registers audit tables in Base.metadata
import app.core.outbox.models  # noqa: F401 — registers outbox tables in Base.metadata
import app.modules.maker_checker.models  # noqa: F401 — registers maker-checker tables in Base.metadata
from alembic import context
from app.core.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_DATABASE_URL = os.environ["DATABASE_URL"]
_SYNC_URL = re.sub(r"^postgresql\+asyncpg", "postgresql+psycopg2", _DATABASE_URL)

_TENANT_SCHEMA = os.environ.get("TENANT_SCHEMA", "").strip()
if not _TENANT_SCHEMA:
    raise RuntimeError(
        "TENANT_SCHEMA environment variable is required for tenant migrations. "
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
        # _TENANT_SCHEMA is validated above — safe to interpolate.
        connection.execute(text(f"SET search_path TO {_TENANT_SCHEMA}"))  # noqa: S608
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=False,
            version_table="alembic_version",
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
