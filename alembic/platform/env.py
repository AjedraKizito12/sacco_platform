"""Alembic env for the platform schema.

Reads DATABASE_URL from the environment, swaps asyncpg -> psycopg2 for
Alembic's synchronous migration runner, and sets search_path=platform
before running migrations.
"""
import os
import re
from logging.config import fileConfig

from sqlalchemy import create_engine, pool, text

# Import Base so platform model metadata is available.
# (Initially empty; add `from app.modules.platform_.models import *` as
# platform models are created.)
import app.core.audit.models  # noqa: F401 — registers audit tables in Base.metadata
import app.core.outbox.models  # noqa: F401 — registers outbox tables in Base.metadata
import app.modules.maker_checker.models  # noqa: F401 — registers maker-checker tables in Base.metadata
import app.platform_.models  # noqa: F401 — registers platform_ tables in Base.metadata
from alembic import context
from app.core.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_DATABASE_URL = os.environ["DATABASE_URL"]
_SYNC_URL = re.sub(r"^postgresql\+asyncpg", "postgresql+psycopg2", _DATABASE_URL)


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section) or {}
    cfg["sqlalchemy.url"] = _SYNC_URL

    connectable = create_engine(
        _SYNC_URL,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        connection.execute(text("SET search_path TO platform"))
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema="platform",
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
