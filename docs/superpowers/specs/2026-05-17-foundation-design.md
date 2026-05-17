# SACCO Platform — Foundation Design

**Date:** 2026-05-17
**Status:** Approved
**Scope:** Project bootstrapping — infrastructure config, core app scaffolding, DB layer, Alembic setup

---

## 1. Overview

Establish the project skeleton that every bounded-context module will build on. No business logic lives here — only the machinery every module depends on: dependency management, containerisation, configuration, async DB access with multi-tenant search_path switching, structured logging, and Alembic migration harness.

---

## 2. Files Created

| File | Purpose |
|---|---|
| `pyproject.toml` | Pinned deps, ruff, mypy |
| `docker-compose.yml` | All infra services + api |
| `Dockerfile` | Multi-stage, non-root |
| `.env.example` | Every required env var |
| `app/main.py` | FastAPI app, middleware, health endpoints |
| `app/core/config.py` | pydantic-settings singleton |
| `app/core/db.py` | Async engine, session factory, tenant session dependency |
| `alembic/platform/env.py` | Platform-schema migrations |
| `alembic/tenant/env.py` | Per-tenant migrations (hard-fails if TENANT_SCHEMA unset) |
| `alembic.ini` | Two config sections: platform + tenant |
| `scripts/migrate_all_tenants.py` | Iterate all tenants, run tenant migrations |

---

## 3. Dependencies (`pyproject.toml`)

**Build backend:** Hatch. **Python:** ≥3.11.

### Runtime (pinned exact)

| Package | Version |
|---|---|
| fastapi | 0.115.5 |
| uvicorn[standard] | 0.32.1 |
| sqlalchemy | 2.0.36 |
| alembic | 1.14.0 |
| asyncpg | 0.30.0 |
| pydantic | 2.10.3 |
| pydantic-settings | 2.7.0 |
| celery[redis] | 5.4.0 |
| redis | 5.2.1 |
| aio-pika | 9.4.3 |
| elasticsearch | 8.17.0 |
| structlog | 24.4.0 |
| python-jose[cryptography] | 3.3.0 |
| passlib[bcrypt] | 1.7.4 |

### Dev

pytest, pytest-asyncio, factory-boy, httpx, ruff, mypy, types-passlib, types-python-jose, psycopg2-binary (needed by Alembic's sync migration runner and `migrate_all_tenants.py`)

### ruff

```toml
line-length = 100
target-version = "py311"
select = ["E", "W", "F", "I", "B", "UP", "SIM", "TCH"]
```

### mypy

```toml
strict = true
plugins = ["pydantic.mypy"]
ignore_missing_imports = false
```

---

## 4. Docker Compose

**Network:** `sacco_net` (bridge). All services attach to it.

**Services:**

| Service | Image | Port(s) | Volume | Health check |
|---|---|---|---|---|
| postgres | postgres:16 | 5432 | pgdata | `pg_isready -U $POSTGRES_USER` |
| redis | redis:7 | 6379 | redisdata | `redis-cli ping` |
| rabbitmq | rabbitmq:3.12-management | 5672, 15672 | rabbitmqdata | `rabbitmq-diagnostics ping` |
| elasticsearch | elasticsearch:8.17.0 | 9200 | esdata | `curl -sf http://localhost:9200/_cluster/health` |
| api | build: . | 8000 | — | depends on all four healthy |

ES runs single-node with `xpack.security.enabled=false` for local dev.

---

## 5. Dockerfile

**Stage 1 — `builder`:** `python:3.11-slim`. Install build tools. `pip install --prefix=/install` from `pyproject.toml`.

**Stage 2 — `runtime`:** `python:3.11-slim`. Copy `/install`. Create `appuser:appgroup` (uid/gid 1000). `WORKDIR /app`. Copy app source. `USER appuser`. `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`.

---

## 6. Environment Variables (`.env.example`)

```
# Database
DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5432/sacco

# Redis
REDIS_URL=redis://localhost:6379/0

# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# Elasticsearch
ELASTICSEARCH_URL=http://localhost:9200

# App
APP_SECRET_KEY=change-me-in-production
APP_ENV=development
LOG_LEVEL=INFO
ALLOWED_ORIGINS=http://localhost:3000

# DB pool
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20

# Observability
STRUCTLOG_JSON=false
SLOW_QUERY_MS=200

# Headers
REQUEST_ID_HEADER=X-Request-ID
TENANT_HEADER=X-Tenant-Slug
```

---

## 7. `app/main.py`

**Lifespan:** Startup creates Redis connection pool; shutdown closes it.

**Middleware (applied in order):**
1. `CORSMiddleware` — origins from `settings.allowed_origins`
2. `RequestIDMiddleware` — reads `REQUEST_ID_HEADER` or generates UUID4; binds to structlog context
3. Slow-query logging via SQLAlchemy event hook (not middleware) — logs queries > `SLOW_QUERY_MS`

**Global exception handler:** catches unhandled `Exception`, logs with structlog, returns `{"detail": "internal server error"}` with 500.

**Endpoints:**
- `GET /healthz` — liveness probe. Returns `{"status": "ok"}` immediately. Never checks dependencies. Always 200.
- `GET /readyz` — readiness probe. Concurrently checks:
  - Postgres: `SELECT 1`
  - Redis: `PING`
  - RabbitMQ: open + close aio-pika connection
  - Elasticsearch: `/_cluster/health?timeout=2s`
  - Returns `{"status": "ok"|"degraded", "checks": {"postgres": "ok"|"error: ...", ...}}`
  - HTTP 200 if all pass, 503 if any fail.

---

## 8. `app/core/config.py`

`Settings(BaseSettings)` with `SettingsConfigDict(env_file=".env", case_sensitive=False)`.

Fields: all env vars listed in §6. Singleton via `@lru_cache` on `get_settings()`.

---

## 9. `app/core/db.py`

### Engine & session factory

```python
engine = create_async_engine(settings.database_url, pool_size=..., max_overflow=...)
AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)
Base = DeclarativeBase()
```

### `get_tenant_session` dependency

1. Read slug from `settings.tenant_header` request header. 400 if missing.
2. Validate slug: `^[a-z0-9-]{1,40}$`. 400 if invalid.
3. Look up `schema_name` in Redis: key `tenant:slug:<slug>:schema`. On miss, query `platform.tenants` table; cache result with TTL 300 s. 404 if no tenant found.
4. Validate looked-up schema name: `^tenant_[a-z0-9_]{1,40}$`. 500 (log alert) if invalid — defense in depth against corrupted data.
5. Yield `AsyncSession` after executing `SET LOCAL search_path TO <schema_name>, platform`.
6. Session closed in `finally`.

### `get_platform_session` dependency

Yields `AsyncSession` after `SET LOCAL search_path TO platform`.

### Note on search_path

`public` is **not** included in any `search_path`. All shared objects (extensions, etc.) are created in `platform` schema.

---

## 10. Alembic

### Directory structure

```
alembic/
  platform/
    env.py
    script.py.mako
    versions/
  tenant/
    env.py
    script.py.mako
    versions/
alembic.ini
```

### `alembic.ini` / `alembic-tenant.ini`

Two separate ini files:
- `alembic.ini` — points to `alembic/platform/`. Default for `alembic upgrade head`.
- `alembic-tenant.ini` — points to `alembic/tenant/`. Used as `alembic -c alembic-tenant.ini upgrade head`.

### `alembic/platform/env.py`

- Imports `Base` (initially empty — populated as platform models are added)
- Sets `search_path` to `platform` before running migrations
- Uses synchronous psycopg2 connection (via `DATABASE_URL` with scheme swapped to `postgresql+psycopg2`)

### `alembic/tenant/env.py`

- Reads `TENANT_SCHEMA` from environment. **Hard-fails with `RuntimeError`** if unset or blank.
- Validates `TENANT_SCHEMA` against `^tenant_[a-z0-9_]{1,40}$` — hard-fails if invalid.
- Sets `search_path` to the validated schema before running migrations.

### `scripts/migrate_all_tenants.py`

Queries `SELECT schema_name FROM platform.tenants` (synchronous psycopg2 connection, no ORM). For each row, shells out: `TENANT_SCHEMA=<schema> alembic -n tenant upgrade head`. Logs success/failure per tenant. Exits non-zero if any tenant fails.

---

## 11. Security Decisions

- Tenant slug from header only. No slug in URL path (avoids routing conflicts with future versioned APIs).
- Schema name is never derived from user input — always looked up from DB, validated independently.
- Non-root Docker user prevents container escape privilege escalation.
- `APP_SECRET_KEY` must be changed before production — no default that looks safe.

---

## 12. Out of Scope (this spec)

- JWT / authentication (IAM module, built later)
- Celery worker configuration
- Outbox/event publishing
- Any business model or migration
