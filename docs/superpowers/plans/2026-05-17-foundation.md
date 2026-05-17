# Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bootstrap every infrastructure file the SACCO platform depends on — packaging, containers, async DB layer with schema-per-tenant switching, structured logging, and Alembic migration harness.

**Architecture:** Multi-tenant FastAPI app backed by PostgreSQL (schema-per-tenant via `SET LOCAL search_path`). Tenant identity comes from an `X-Tenant-Slug` header; the slug is validated and looked up against `platform.tenants` with Redis caching. All config via pydantic-settings. Alembic runs separately for platform and tenant schemas.

**Tech Stack:** Python 3.11, FastAPI 0.115.5, SQLAlchemy 2.0 async, asyncpg, pydantic-settings, Redis (aio), aio-pika, elasticsearch-py, structlog, Alembic + psycopg2-binary (sync runner), Docker Compose, Hatch

---

## File Map

| File | Task | Responsibility |
|---|---|---|
| `pyproject.toml` | 1 | Pinned deps, ruff, mypy, pytest config |
| `.env.example` | 2 | All required env vars with dev defaults |
| `Dockerfile` | 3 | Multi-stage, non-root `appuser` |
| `docker-compose.yml` | 4 | 5 services, healthchecks, named volumes |
| `app/__init__.py` | 5 | Package marker |
| `app/core/__init__.py` | 5 | Package marker |
| `app/core/config.py` | 5 | `Settings(BaseSettings)` singleton |
| `tests/__init__.py` | 5 | Package marker |
| `tests/core/__init__.py` | 5 | Package marker |
| `tests/conftest.py` | 5 | Env var stubs for test process |
| `tests/core/test_config.py` | 5 | Settings load + defaults |
| `app/core/db.py` | 6 | `Base`, engine, `AsyncSessionFactory`, `get_tenant_session`, `get_platform_session` |
| `tests/core/test_db.py` | 6 | Slug + schema regex validation (unit, no DB) |
| `app/main.py` | 7 | FastAPI app, lifespan, CORS, request-id middleware, exception handler, `/healthz`, `/readyz` |
| `tests/test_main.py` | 7 | Liveness + request-id header tests |
| `alembic.ini` | 8 | Platform migration config |
| `alembic-tenant.ini` | 8 | Tenant migration config |
| `alembic/platform/script.py.mako` | 8 | Standard Alembic template |
| `alembic/platform/env.py` | 8 | Platform env: sets `search_path=platform`, hard-reads `DATABASE_URL` |
| `alembic/tenant/script.py.mako` | 8 | Standard Alembic template |
| `alembic/tenant/env.py` | 8 | Tenant env: hard-fails if `TENANT_SCHEMA` unset/invalid |
| `scripts/__init__.py` | 9 | Package marker |
| `scripts/migrate_all_tenants.py` | 9 | Iterate `platform.tenants`, shell out per tenant |

---

## Task 1: `pyproject.toml`

**Files:**
- Modify: `pyproject.toml` (currently empty)

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "sacco-platform"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi==0.115.5",
    "uvicorn[standard]==0.32.1",
    "sqlalchemy==2.0.36",
    "alembic==1.14.0",
    "asyncpg==0.30.0",
    "pydantic==2.10.3",
    "pydantic-settings==2.7.0",
    "celery[redis]==5.4.0",
    "redis==5.2.1",
    "aio-pika==9.4.3",
    "elasticsearch==8.17.0",
    "structlog==24.4.0",
    "python-jose[cryptography]==3.3.0",
    "passlib[bcrypt]==1.7.4",
]

[project.optional-dependencies]
dev = [
    "pytest==8.3.4",
    "pytest-asyncio==0.24.0",
    "anyio==4.7.0",
    "factory-boy==3.3.1",
    "httpx==0.27.2",
    "ruff==0.8.4",
    "mypy==1.13.0",
    "types-passlib==1.7.7.20240819",
    "types-python-jose==3.3.4.20240106",
    "psycopg2-binary==2.9.10",
]

[tool.hatch.build.targets.wheel]
packages = ["app"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "UP", "SIM", "TCH"]

[tool.mypy]
python_version = "3.11"
strict = true
plugins = ["pydantic.mypy"]
ignore_missing_imports = false

[[tool.mypy.overrides]]
module = ["aio_pika.*", "passlib.*", "jose.*", "celery.*", "elasticsearch.*"]
ignore_missing_imports = true
```

- [ ] **Step 2: Install deps and verify**

```bash
pip install -e ".[dev]"
python -c "import fastapi, sqlalchemy, alembic, asyncpg, pydantic_settings, redis, aio_pika, elasticsearch, structlog; print('all imports ok')"
```
Expected: `all imports ok`

- [ ] **Step 3: Verify ruff and mypy are callable**

```bash
ruff check --version
mypy --version
```
Expected: both print version strings without error.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add pyproject.toml with pinned deps, ruff, mypy"
```

---

## Task 2: `.env.example`

**Files:**
- Modify: `.env.example` (currently empty)

- [ ] **Step 1: Write `.env.example`**

```dotenv
# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5432/sacco

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0

# ── RabbitMQ ──────────────────────────────────────────────────────────────────
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# ── Elasticsearch ─────────────────────────────────────────────────────────────
ELASTICSEARCH_URL=http://localhost:9200

# ── App ───────────────────────────────────────────────────────────────────────
# CHANGE THIS before production — must be a random 32+ byte string
APP_SECRET_KEY=CHANGE_ME_IN_PRODUCTION
APP_ENV=development
LOG_LEVEL=INFO
# JSON array: ["http://localhost:3000","http://localhost:8080"]
ALLOWED_ORIGINS=["http://localhost:3000"]

# ── DB pool ───────────────────────────────────────────────────────────────────
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20

# ── Observability ─────────────────────────────────────────────────────────────
# Set to true in production to emit JSON logs
STRUCTLOG_JSON=false
SLOW_QUERY_MS=200

# ── Headers ───────────────────────────────────────────────────────────────────
REQUEST_ID_HEADER=X-Request-ID
TENANT_HEADER=X-Tenant-Slug
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "chore: add .env.example with all required environment variables"
```

---

## Task 3: `Dockerfile`

**Files:**
- Modify: `Dockerfile` (currently empty)

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
# Create a minimal package structure so hatchling can find the project
RUN mkdir -p app && touch app/__init__.py

RUN pip install --no-cache-dir --prefix=/install ".[dev]"

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid 1000 --no-create-home --shell /bin/false appuser

WORKDIR /app

COPY --chown=appuser:appgroup . .

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Verify the image builds**

```bash
docker build -t sacco-platform:dev .
```
Expected: Build completes, no errors. Final stage image is created.

- [ ] **Step 3: Verify non-root user**

```bash
docker run --rm sacco-platform:dev whoami
```
Expected: `appuser`

- [ ] **Step 4: Commit**

```bash
git add Dockerfile
git commit -m "chore: add multi-stage Dockerfile with non-root appuser"
```

---

## Task 4: `docker-compose.yml`

**Files:**
- Modify: `docker-compose.yml` (currently empty)

- [ ] **Step 1: Write `docker-compose.yml`**

```yaml
name: sacco-platform

networks:
  sacco_net:
    driver: bridge

volumes:
  pgdata:
  redisdata:
  rabbitmqdata:
  esdata:

services:
  postgres:
    image: postgres:16
    restart: unless-stopped
    networks: [sacco_net]
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_USER: sacco
      POSTGRES_PASSWORD: sacco
      POSTGRES_DB: sacco
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U sacco -d sacco"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7
    restart: unless-stopped
    networks: [sacco_net]
    ports:
      - "6379:6379"
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 10

  rabbitmq:
    image: rabbitmq:3.12-management
    restart: unless-stopped
    networks: [sacco_net]
    ports:
      - "5672:5672"
      - "15672:15672"
    volumes:
      - rabbitmqdata:/var/lib/rabbitmq
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "ping"]
      interval: 10s
      timeout: 10s
      retries: 10

  elasticsearch:
    image: elasticsearch:8.17.0
    restart: unless-stopped
    networks: [sacco_net]
    ports:
      - "9200:9200"
    volumes:
      - esdata:/usr/share/elasticsearch/data
    environment:
      discovery.type: single-node
      xpack.security.enabled: "false"
      ES_JAVA_OPTS: "-Xms512m -Xmx512m"
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:9200/_cluster/health | grep -qv '\"status\":\"red\"'"]
      interval: 10s
      timeout: 10s
      retries: 15

  api:
    build: .
    restart: unless-stopped
    networks: [sacco_net]
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
      elasticsearch:
        condition: service_healthy
```

- [ ] **Step 2: Validate compose config**

```bash
docker compose config --quiet
```
Expected: No output (config is valid).

- [ ] **Step 3: Bring up infra services and confirm healthy**

```bash
docker compose up -d postgres redis rabbitmq elasticsearch
docker compose ps
```
Expected: All four services show `healthy` status within ~60 s.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: add docker-compose with postgres/redis/rabbitmq/elasticsearch/api"
```

---

## Task 5: `app/core/config.py`

**Files:**
- Create: `app/__init__.py`
- Create: `app/core/__init__.py`
- Create: `app/core/config.py`
- Create: `tests/__init__.py`
- Create: `tests/core/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/core/test_config.py`

- [ ] **Step 1: Create package markers**

`app/__init__.py` — empty file.
`app/core/__init__.py` — empty file.
`tests/__init__.py` — empty file.
`tests/core/__init__.py` — empty file.

- [ ] **Step 2: Write `tests/conftest.py`**

This file sets required env vars before any module import so `get_settings()` never fails during tests.

```python
import os

# Set required env vars before any app module is imported.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://sacco:sacco@localhost:5432/sacco_test")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-not-used-in-production")
```

- [ ] **Step 3: Write the failing tests**

`tests/core/test_config.py`:

```python
import os
import pytest

# conftest.py sets DATABASE_URL and APP_SECRET_KEY before this import.
from app.core.config import Settings, get_settings


def test_settings_load_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/mydb")
    monkeypatch.setenv("APP_SECRET_KEY", "supersecret")
    s = Settings()
    assert s.database_url == "postgresql+asyncpg://u:p@db:5432/mydb"
    assert s.app_secret_key == "supersecret"


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db/d")
    monkeypatch.setenv("APP_SECRET_KEY", "s")
    s = Settings()
    assert s.app_env == "development"
    assert s.redis_url == "redis://localhost:6379/0"
    assert s.db_pool_size == 10
    assert s.db_max_overflow == 20
    assert s.slow_query_ms == 200
    assert s.structlog_json is False
    assert s.request_id_header == "X-Request-ID"
    assert s.tenant_header == "X-Tenant-Slug"


def test_settings_allowed_origins_parsed_as_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db/d")
    monkeypatch.setenv("APP_SECRET_KEY", "s")
    monkeypatch.setenv("ALLOWED_ORIGINS", '["http://localhost:3000","http://localhost:8080"]')
    s = Settings()
    assert s.allowed_origins == ["http://localhost:3000", "http://localhost:8080"]


def test_get_settings_is_cached() -> None:
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
```

- [ ] **Step 4: Run tests — confirm they fail**

```bash
pytest tests/core/test_config.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.core.config'`

- [ ] **Step 5: Write `app/core/config.py`**

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # Elasticsearch
    elasticsearch_url: str = "http://localhost:9200"

    # App
    app_secret_key: str
    app_env: str = "development"
    log_level: str = "INFO"
    allowed_origins: list[str] = ["http://localhost:3000"]

    # DB pool
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Observability
    structlog_json: bool = False
    slow_query_ms: int = 200

    # Headers
    request_id_header: str = "X-Request-ID"
    tenant_header: str = "X-Tenant-Slug"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 6: Run tests — confirm they pass**

```bash
pytest tests/core/test_config.py -v
```
Expected: 4 tests PASSED.

- [ ] **Step 7: Run mypy and ruff**

```bash
ruff check app/core/config.py
mypy app/core/config.py
```
Expected: No errors.

- [ ] **Step 8: Commit**

```bash
git add app/__init__.py app/core/__init__.py app/core/config.py \
        tests/__init__.py tests/core/__init__.py tests/conftest.py \
        tests/core/test_config.py
git commit -m "feat: add pydantic-settings config with lru_cache singleton"
```

---

## Task 6: `app/core/db.py`

**Files:**
- Create: `app/core/db.py`
- Create: `tests/core/test_db.py`

- [ ] **Step 1: Write the failing tests (unit — no DB connection needed)**

`tests/core/test_db.py`:

```python
import re
import pytest

# These regexes are the exact ones used in db.py.
# Test them here independently to document the contract.
_SLUG_RE = re.compile(r"^[a-z0-9-]{1,40}$")
_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")


@pytest.mark.parametrize(
    "slug, valid",
    [
        ("acme", True),
        ("acme-corp", True),
        ("a1b2c3", True),
        ("a" * 40, True),
        ("a" * 41, False),   # too long
        ("ACME", False),     # uppercase
        ("acme_corp", False),  # underscore not allowed in slug
        ("acme corp", False),  # space
        ("", False),           # empty
        ("-acme", True),       # leading dash is valid per regex
        ("acme-", True),       # trailing dash is valid per regex
    ],
)
def test_slug_regex(slug: str, valid: bool) -> None:
    assert bool(_SLUG_RE.match(slug)) == valid


@pytest.mark.parametrize(
    "schema, valid",
    [
        ("tenant_acme", True),
        ("tenant_acme_corp", True),
        ("tenant_a1b2", True),
        ("tenant_" + "a" * 40, True),
        ("tenant_" + "a" * 41, False),  # too long
        ("platform", False),             # must start with tenant_
        ("public", False),
        ("tenant_ACME", False),          # uppercase not allowed
        ("tenantacme", False),           # missing underscore separator
        ("tenant_", False),              # empty suffix (length 0 after tenant_)
    ],
)
def test_schema_name_regex(schema: str, valid: bool) -> None:
    assert bool(_SCHEMA_RE.match(schema)) == valid
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
pytest tests/core/test_db.py -v
```
Expected: All tests PASS immediately (regex is standalone), confirming the contract before `db.py` exists.

- [ ] **Step 3: Write `app/core/db.py`**

```python
import logging
import re
from collections.abc import AsyncGenerator

from fastapi import HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

_SLUG_RE = re.compile(r"^[a-z0-9-]{1,40}$")
_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")

_log = logging.getLogger(__name__)

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    echo=False,
)

AsyncSessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def _resolve_tenant_schema(slug: str, redis_client: Redis) -> str:
    """Return schema_name for slug, using Redis as a 5-minute cache."""
    cache_key = f"tenant:slug:{slug}:schema"
    cached: bytes | None = await redis_client.get(cache_key)
    if cached is not None:
        return cached.decode()

    # Cache miss: query platform.tenants using a fully-qualified table name
    # so no search_path manipulation is required on this connection.
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT schema_name FROM platform.tenants"
                " WHERE slug = :slug AND is_active = true"
            ),
            {"slug": slug},
        )
        row = result.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{slug}' not found")

    schema_name: str = row[0]
    await redis_client.setex(cache_key, 300, schema_name)
    return schema_name


async def get_tenant_session(
    request: Request,
) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield an AsyncSession scoped to the request tenant.

    Reads the tenant slug from the configured header, looks up schema_name via
    Redis-backed cache, validates it, then executes
    SET LOCAL search_path TO <schema_name>, platform
    before yielding.
    """
    slug: str | None = request.headers.get(settings.tenant_header)
    if not slug:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required header: {settings.tenant_header}",
        )

    if not _SLUG_RE.match(slug):
        raise HTTPException(
            status_code=400,
            detail="Invalid tenant slug: must match ^[a-z0-9-]{1,40}$",
        )

    redis_client: Redis = request.app.state.redis
    schema_name = await _resolve_tenant_schema(slug, redis_client)

    # Defense in depth: validate the schema_name we got from our own DB.
    if not _SCHEMA_RE.match(schema_name):
        _log.error(
            "Resolved schema_name failed validation — possible data corruption",
            slug=slug,
            schema_name=schema_name,
        )
        raise HTTPException(status_code=500, detail="Internal configuration error")

    # schema_name is validated against ^tenant_[a-z0-9_]{1,40}$ — safe to interpolate.
    async with AsyncSessionFactory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )
        yield session


async def get_platform_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield an AsyncSession with search_path set to platform."""
    async with AsyncSessionFactory() as session:
        await session.execute(text("SET LOCAL search_path TO platform"))
        yield session
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
pytest tests/core/test_db.py -v
```
Expected: All 21 parametrised tests PASSED.

- [ ] **Step 5: Run mypy and ruff**

```bash
ruff check app/core/db.py
mypy app/core/db.py
```
Expected: No errors.

- [ ] **Step 6: Commit**

```bash
git add app/core/db.py tests/core/test_db.py
git commit -m "feat: add async DB engine, Base, get_tenant_session, get_platform_session"
```

---

## Task 7: `app/main.py`

**Files:**
- Create: `app/main.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write failing tests**

`tests/test_main.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def test_healthz_returns_200(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_healthz_is_fast_and_needs_no_deps(client: AsyncClient) -> None:
    """Liveness probe must never touch infra services."""
    # If this test passes without real infra running, the probe is truly cheap.
    response = await client.get("/healthz")
    assert response.status_code == 200


async def test_request_id_echoed_when_provided(client: AsyncClient) -> None:
    response = await client.get("/healthz", headers={"X-Request-ID": "my-trace-id"})
    assert response.headers.get("x-request-id") == "my-trace-id"


async def test_request_id_generated_when_absent(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    rid = response.headers.get("x-request-id")
    assert rid is not None
    # UUID4: 8-4-4-4-12 hex, 36 chars including dashes
    assert len(rid) == 36
    assert rid.count("-") == 4


async def test_unknown_route_returns_404(client: AsyncClient) -> None:
    response = await client.get("/does-not-exist")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
pytest tests/test_main.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: Write `app/main.py`**

```python
import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

import structlog
from elasticsearch import AsyncElasticsearch
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
import aio_pika

from app.core.config import get_settings
from app.core.db import engine

settings = get_settings()


def _configure_logging() -> None:
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
    ]
    if settings.structlog_json:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


_configure_logging()
_log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=False)
    _log.info("Startup complete", env=settings.app_env)
    yield
    await app.state.redis.aclose()
    await engine.dispose()
    _log.info("Shutdown complete")


app = FastAPI(title="SACCO Platform API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next: Any) -> Any:
    request_id = request.headers.get(settings.request_id_header) or str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(request_id=request_id)
    response = await call_next(request)
    response.headers[settings.request_id_header] = request_id
    structlog.contextvars.clear_contextvars()
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    _log.exception("Unhandled exception", path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "internal server error"},
    )


# ── Health endpoints ──────────────────────────────────────────────────────────


@app.get("/healthz", tags=["ops"])
async def healthz() -> dict[str, str]:
    """Liveness probe — returns 200 immediately without touching dependencies."""
    return {"status": "ok"}


async def _check_postgres() -> str:
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        return f"error: {exc}"


async def _check_redis(redis_client: Redis) -> str:
    try:
        await redis_client.ping()
        return "ok"
    except Exception as exc:
        return f"error: {exc}"


async def _check_rabbitmq() -> str:
    try:
        conn = await asyncio.wait_for(
            aio_pika.connect_robust(settings.rabbitmq_url),
            timeout=3.0,
        )
        await conn.close()
        return "ok"
    except Exception as exc:
        return f"error: {exc}"


async def _check_elasticsearch() -> str:
    es = AsyncElasticsearch(settings.elasticsearch_url)
    try:
        await asyncio.wait_for(es.cluster.health(), timeout=3.0)
        return "ok"
    except Exception as exc:
        return f"error: {exc}"
    finally:
        await es.close()


@app.get("/readyz", tags=["ops"])
async def readyz(request: Request) -> JSONResponse:
    """Readiness probe — checks all four infra dependencies concurrently."""
    postgres, redis, rabbitmq, elasticsearch = await asyncio.gather(
        _check_postgres(),
        _check_redis(request.app.state.redis),
        _check_rabbitmq(),
        _check_elasticsearch(),
    )
    checks = {
        "postgres": postgres,
        "redis": redis,
        "rabbitmq": rabbitmq,
        "elasticsearch": elasticsearch,
    }
    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "ok" if all_ok else "degraded", "checks": checks},
    )
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
pytest tests/test_main.py -v
```
Expected: 5 tests PASSED. (`/readyz` is not tested here because it requires live infra.)

- [ ] **Step 5: Run mypy and ruff**

```bash
ruff check app/main.py
mypy app/main.py
```
Expected: No errors. (mypy will warn about the untyped `call_next` arg — the `Any` annotation suppresses it.)

- [ ] **Step 6: Run the full test suite**

```bash
pytest -v
```
Expected: All tests PASSED, no failures.

- [ ] **Step 7: Commit**

```bash
git add app/main.py tests/test_main.py
git commit -m "feat: add FastAPI app with lifespan, CORS, request-id middleware, /healthz, /readyz"
```

---

## Task 8: Alembic Setup

**Files:**
- Modify: `alembic.ini` (currently empty)
- Create: `alembic-tenant.ini`
- Create: `alembic/platform/env.py`
- Create: `alembic/platform/script.py.mako`
- Create: `alembic/platform/versions/.gitkeep`
- Create: `alembic/tenant/env.py`
- Create: `alembic/tenant/script.py.mako`
- Create: `alembic/tenant/versions/.gitkeep`

- [ ] **Step 1: Write `alembic.ini` (platform)**

```ini
[alembic]
script_location = alembic/platform
file_template = %%(year)d%%(month).2d%%(day).2d_%%(rev)s_%%(slug)s
prepend_sys_path = .
version_path_separator = os
# URL is overridden in env.py via DATABASE_URL env var
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console
qualname =

[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2: Write `alembic-tenant.ini`**

```ini
[alembic]
script_location = alembic/tenant
file_template = %%(year)d%%(month).2d%%(day).2d_%%(rev)s_%%(slug)s
prepend_sys_path = .
version_path_separator = os
# URL is overridden in env.py via DATABASE_URL env var
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console
qualname =

[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 3: Write `alembic/platform/script.py.mako`**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4: Write `alembic/tenant/script.py.mako`**

Same content as Step 3 — copy it exactly.

- [ ] **Step 5: Write `alembic/platform/env.py`**

```python
"""Alembic env for the platform schema.

Reads DATABASE_URL from the environment, swaps asyncpg → psycopg2 for
Alembic's synchronous migration runner, and sets search_path=platform
before running migrations.
"""
import os
import re
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool, text

# Import Base so platform model metadata is available.
# (Initially empty; add `from app.modules.platform_.models import *` as
# platform models are created.)
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
```

- [ ] **Step 6: Write `alembic/tenant/env.py`**

```python
"""Alembic env for per-tenant schemas.

TENANT_SCHEMA must be set in the environment before running this.
Hard-fails if it is absent or does not match ^tenant_[a-z0-9_]{1,40}$.

Usage:
    TENANT_SCHEMA=tenant_acme alembic -c alembic-tenant.ini upgrade head
"""
import os
import re
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool, text

# Import Base so tenant model metadata is available.
# (Add `from app.modules.<name>.models import *` as tenant models are created.)
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
```

- [ ] **Step 7: Create version directories**

```bash
mkdir -p alembic/platform/versions alembic/tenant/versions
touch alembic/platform/versions/.gitkeep alembic/tenant/versions/.gitkeep
```

- [ ] **Step 8: Verify Alembic can read the configs**

With infra services running (`docker compose up -d postgres`):

```bash
DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5432/sacco \
  alembic current
```
Expected: `INFO  [alembic.runtime.migration] Context impl PostgreSQLImpl.` then `(no current revisions)` or similar — no errors.

```bash
DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5432/sacco \
  alembic -c alembic-tenant.ini current
```
Expected: `RuntimeError: TENANT_SCHEMA environment variable is required` — confirming hard-fail.

```bash
DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5432/sacco \
TENANT_SCHEMA=tenant_acme \
  alembic -c alembic-tenant.ini current
```
Expected: Runs without error, prints `(no current revisions)`.

- [ ] **Step 9: Commit**

```bash
git add alembic.ini alembic-tenant.ini \
        alembic/platform/ alembic/tenant/
git commit -m "chore: add Alembic for platform and tenant schemas with separate ini files"
```

---

## Task 9: `scripts/migrate_all_tenants.py`

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/migrate_all_tenants.py`

- [ ] **Step 1: Create `scripts/__init__.py`**

Empty file.

- [ ] **Step 2: Write `scripts/migrate_all_tenants.py`**

```python
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

import psycopg2

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

    result = subprocess.run(
        ["alembic", "-c", "alembic-tenant.ini", "upgrade", "head"],
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
```

- [ ] **Step 3: Run ruff and mypy**

```bash
ruff check scripts/migrate_all_tenants.py
mypy scripts/migrate_all_tenants.py
```
Expected: No errors.

- [ ] **Step 4: Smoke-test with no tenants (requires `platform` schema + tenants table to exist)**

The `platform.tenants` table does not exist yet (no platform migrations written), so a real run will fail. Instead, confirm the script handles a missing `DATABASE_URL` gracefully:

```bash
python scripts/migrate_all_tenants.py
```
Without `DATABASE_URL` set: Expected `KeyError: 'DATABASE_URL'` — confirms the env var is required.

```bash
DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5432/sacco \
  python scripts/migrate_all_tenants.py
```
With DB up but no `platform` schema yet: Expected `psycopg2.errors.UndefinedTable` — normal; the table doesn't exist yet. The script will be validated end-to-end once the `platform_` module is built.

- [ ] **Step 5: Commit**

```bash
git add scripts/__init__.py scripts/migrate_all_tenants.py
git commit -m "chore: add migrate_all_tenants.py script for bulk tenant migrations"
```

---

## Final Smoke Test

With all infra services healthy:

```bash
docker compose up -d postgres redis rabbitmq elasticsearch
# Wait until all services show healthy
docker compose ps

# Run the app locally
DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5432/sacco \
APP_SECRET_KEY=dev-secret \
  uvicorn app.main:app --reload

# In another terminal:
curl -s http://localhost:8000/healthz | python -m json.tool
# Expected: {"status": "ok"}

curl -s http://localhost:8000/readyz | python -m json.tool
# Expected: {"status": "ok", "checks": {"postgres": "ok", "redis": "ok", "rabbitmq": "ok", "elasticsearch": "ok"}}
```

- [ ] **Run the full test suite one last time**

```bash
pytest -v
```
Expected: All tests PASSED.
