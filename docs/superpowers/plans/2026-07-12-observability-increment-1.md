# Phase 5 Observability — Increment 1 (App Instrumentation + Local LGTM) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Structured JSON logging with secret scrubbing, Prometheus metrics + a `/metrics` endpoint, business-metric gauges pushed from a Celery beat task to a Pushgateway, an OpenTelemetry tracing scaffold (no-op unless configured), and a self-hosted LGTM stack behind an opt-in Docker Compose profile — all verified locally.

**Architecture:** All new app code lives in `app/core/observability/` (cross-cutting). A structlog processor redacts sensitive keys in every log config (app + workers). A metrics registry + HTTP middleware feed `/metrics`; a 60s beat task pushes business gauges to a Pushgateway. OTEL instruments FastAPI/SQLAlchemy/Celery only when the OTLP endpoint env var is set. Loki/Grafana/Tempo/Prometheus/Pushgateway/OTEL-Collector run under a `observability` compose profile.

**Tech Stack:** Python 3.11, FastAPI, structlog, prometheus-client, opentelemetry-sdk + OTLP exporter + FastAPI/SQLAlchemy/Celery instrumentation, Celery, Docker Compose, self-hosted LGTM.

**Spec:** `docs/superpowers/specs/2026-07-12-observability-monitoring-design.md`

Branch: `feat/observability-inc1` (from `main`).

## Global Constraints

- **All new app code under `app/core/observability/`.** It imports nothing from `app/modules` or `app/platform_` except through existing read services for business gauges. No new tables, no migration.
- **New dependencies are additive** (never substitute the fixed stack) and MUST be justified in the commit message per CLAUDE.md ("Do not add new top-level dependencies without justification"). Pin exact versions (OTEL pins drift and break at runtime).
- **The secret-scrubbing processor is mandatory** in every logging configuration (the app in `app/main.py` AND the worker in `app/workers/celery_app.py`). Default scrub keys: `password`, `token`, `access_token`, `refresh_token`, `authorization`, `secret`, `jwt_kek`, `hashed_password`, `private_key`, `national_id_number`, `email`, `card_number`. Case-insensitive; also match keys ending `_token`, `_secret`, `_password`. Redaction value: `"[REDACTED]"`.
- **`/metrics` is unauthenticated and NOT subscription-gated** (Prometheus scrapes it); it returns 404 when `settings.metrics_enabled` is false; documented internal-network-only for prod.
- **Metric path labels use the matched route template** (`/platform/tenants/{tenant_id}`), never the raw path, to bound cardinality.
- **Tracing is a no-op when `settings.otel_exporter_otlp_endpoint` is unset** — the default dev stack and the entire test suite must run unchanged.
- **Business gauges push to Pushgateway** from the beat task (workers can't be scraped); the task no-ops when `settings.pushgateway_url` is unset. MRR counts only `active`/`trialing` subscriptions (existing dashboard-stats convention).
- **LGTM services are opt-in** via `profiles: ["observability"]` — they must NOT start on a plain `docker compose up`.
- ruff + mypy (strict) clean; pytest green. This increment is a sanctioned exception to CLAUDE.md contract N (edits `docker-compose.yml`, adds `infra/observability/`, `app/core/observability/`, worker/main wiring, `pyproject.toml`).

## File Structure

```
pyproject.toml                                   (modify: add pinned deps)
app/core/config.py                               (modify: 4 new settings)
app/core/observability/__init__.py               (create)
app/core/observability/logging.py                (create: scrub_sensitive processor)
app/core/observability/metrics.py                (create: registry + metrics + render)
app/core/observability/business_metrics.py       (create: gauge computation + push)
app/core/observability/tracing.py                (create: OTEL scaffold, no-op default)
app/core/observability/beat.py                   (create: emit_business_metrics_gauges task)
app/main.py                                       (modify: scrubber in chain, metrics middleware, /metrics, tracing in lifespan)
app/workers/celery_app.py                        (modify: logging config, tracing, beat entry, include)
tests/core/observability/__init__.py             (create)
tests/core/observability/test_logging.py         (create)
tests/core/observability/test_metrics.py         (create)
tests/core/observability/test_business_metrics.py (create)
tests/core/observability/test_tracing.py         (create)

infra/observability/prometheus/prometheus.yml    (create)
infra/observability/otel-collector/config.yaml   (create)
infra/observability/tempo/tempo.yaml             (create)
infra/observability/loki/loki-config.yaml        (create)
infra/observability/grafana/provisioning/datasources/datasources.yaml (create)
infra/observability/README.md                    (create)
docker-compose.yml                               (modify: observability-profile services)

CLAUDE.md                                         (modify: observability contracts + scope)
```

---

### Task 1: Dependencies + settings

**Files:**
- Modify: `pyproject.toml` (dependencies list), `app/core/config.py`

**Interfaces:**
- Produces: settings `metrics_enabled: bool = True`, `otel_exporter_otlp_endpoint: str | None = None`, `pushgateway_url: str | None = None`, `log_scrub_keys: list[str]` (with the default key set). New importable packages: `prometheus_client`, `opentelemetry` SDK + exporters + instrumentations.

- [ ] **Step 1: Add pinned dependencies**

In `pyproject.toml` `dependencies`, add (verify latest-compatible pins at install time; these are known-good as of writing):
```toml
    "prometheus-client==0.21.1",
    "opentelemetry-sdk==1.29.0",
    "opentelemetry-exporter-otlp-proto-grpc==1.29.0",
    "opentelemetry-instrumentation-fastapi==0.50b0",
    "opentelemetry-instrumentation-sqlalchemy==0.50b0",
    "opentelemetry-instrumentation-celery==0.50b0",
```

- [ ] **Step 2: Install into the venv**

Run: `venv/bin/pip install -e . 2>&1 | tail -5`
Expected: installs the six packages without conflict. If a `0.50b0` instrumentation pin is unavailable, use the matching `0.<NN>b0` for SDK `1.29.0` (instrumentation minor tracks SDK; they release in lockstep) and record the resolved versions.

- [ ] **Step 3: Add settings**

In `app/core/config.py`, in the `# Observability` block after `slow_query_ms`:
```python
    metrics_enabled: bool = True
    otel_exporter_otlp_endpoint: str | None = None
    pushgateway_url: str | None = None
    log_scrub_keys: list[str] = [
        "password", "token", "access_token", "refresh_token",
        "authorization", "secret", "jwt_kek", "hashed_password",
        "private_key", "national_id_number", "email", "card_number",
    ]
```

- [ ] **Step 4: Verify settings load + mypy**

Run: `venv/bin/python -c "from app.core.config import get_settings; s=get_settings(); print(s.metrics_enabled, s.pushgateway_url, len(s.log_scrub_keys))"`
Expected: `True None 12`.
Run: `venv/bin/mypy app/core/config.py`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml app/core/config.py
git commit -m "feat(observability): add prometheus + OTEL deps and settings

New top-level deps (additive, not substituting the fixed stack):
prometheus-client for /metrics; opentelemetry-sdk + OTLP exporter +
fastapi/sqlalchemy/celery instrumentation for tracing. Pinned exact
(OTEL pins drift and break at runtime)."
```

---

### Task 2: Secret-scrubbing log processor

**Files:**
- Create: `app/core/observability/__init__.py`, `app/core/observability/logging.py`
- Test: `tests/core/observability/__init__.py`, `tests/core/observability/test_logging.py`

**Interfaces:**
- Consumes: nothing (pure function).
- Produces: `make_scrub_processor(keys: list[str]) -> Callable[[Any, str, dict], dict]` — a structlog processor that returns the event dict with sensitive values replaced by `"[REDACTED]"`, recursing into nested dicts and lists. `REDACTED = "[REDACTED]"`.

- [ ] **Step 1: Write failing tests**

`tests/core/observability/test_logging.py`:
```python
from __future__ import annotations

from app.core.observability.logging import REDACTED, make_scrub_processor

KEYS = ["password", "token", "jwt_kek", "email", "hashed_password"]


def _scrub(event: dict) -> dict:
    return make_scrub_processor(KEYS)(None, "info", event)


def test_redacts_top_level_key():
    assert _scrub({"password": "hunter2", "user": "ada"}) == {
        "password": REDACTED, "user": "ada",
    }


def test_key_match_is_case_insensitive():
    assert _scrub({"Password": "x", "TOKEN": "y"}) == {
        "Password": REDACTED, "TOKEN": REDACTED,
    }


def test_suffix_match_catches_derived_keys():
    out = _scrub({"reset_token": "abc", "api_secret": "s", "db_password": "p"})
    assert out == {"reset_token": REDACTED, "api_secret": REDACTED, "db_password": REDACTED}


def test_recurses_into_nested_dicts_and_lists():
    out = _scrub({"ctx": {"jwt_kek": "k", "ok": 1}, "items": [{"email": "a@b.c"}]})
    assert out["ctx"]["jwt_kek"] == REDACTED
    assert out["ctx"]["ok"] == 1
    assert out["items"][0]["email"] == REDACTED


def test_non_string_values_still_redacted_when_key_matches():
    assert _scrub({"token": 12345})["token"] == REDACTED


def test_untouched_event_passes_through():
    assert _scrub({"msg": "hello", "count": 3}) == {"msg": "hello", "count": 3}
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/pytest tests/core/observability/test_logging.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`app/core/observability/__init__.py`: empty.
`app/core/observability/logging.py`:
```python
"""structlog processor that redacts sensitive values from log events.

Mandatory in every logging configuration (app + workers). Recurses into
nested dicts and lists so bound context never leaks a secret.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

REDACTED = "[REDACTED]"
_SUFFIXES = ("_token", "_secret", "_password")


def _key_is_sensitive(key: str, lowered_keys: set[str]) -> bool:
    k = key.lower()
    return k in lowered_keys or k.endswith(_SUFFIXES)


def _scrub(value: Any, lowered_keys: set[str]) -> Any:
    if isinstance(value, dict):
        return {
            k: (REDACTED if _key_is_sensitive(str(k), lowered_keys)
                else _scrub(v, lowered_keys))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub(v, lowered_keys) for v in value]
    return value


def make_scrub_processor(
    keys: list[str],
) -> Callable[[Any, str, dict[str, Any]], dict[str, Any]]:
    lowered = {k.lower() for k in keys}

    def processor(
        _logger: Any, _method: str, event_dict: dict[str, Any]
    ) -> dict[str, Any]:
        return _scrub(event_dict, lowered)

    return processor
```

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/pytest tests/core/observability/test_logging.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: mypy + ruff**

Run: `venv/bin/mypy app/core/observability/logging.py && venv/bin/ruff check app/core/observability/`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add app/core/observability/__init__.py app/core/observability/logging.py tests/core/observability/
git commit -m "feat(observability): secret-scrubbing structlog processor"
```

---

### Task 3: Wire the scrubber into app + worker logging

**Files:**
- Modify: `app/main.py` (`_configure_logging`), `app/workers/celery_app.py`

**Interfaces:**
- Consumes: `make_scrub_processor` (Task 2), `settings.log_scrub_keys` (Task 1).
- Produces: both the API and the worker apply the scrubber in their structlog chain, before the renderer.

- [ ] **Step 1: Insert scrubber in the app chain**

In `app/main.py` `_configure_logging()`, import and insert the scrubber after `merge_contextvars` and before the renderer branch:
```python
from app.core.observability.logging import make_scrub_processor
...
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        make_scrub_processor(settings.log_scrub_keys),
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
    ]
```

- [ ] **Step 2: Configure worker logging explicitly**

In `app/workers/celery_app.py`, add a `setup_logging` signal handler (or a direct `_configure_logging` call at import) that applies the SAME chain. Add near the top after `settings = get_settings()`:
```python
import structlog
from typing import Any
from app.core.observability.logging import make_scrub_processor


def _configure_worker_logging() -> None:
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        make_scrub_processor(settings.log_scrub_keys),
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.ExceptionRenderer(),
    ]
    processors.append(
        structlog.processors.JSONRenderer()
        if settings.structlog_json
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


_configure_worker_logging()
```

- [ ] **Step 3: Verify scrubbing end to end (manual smoke)**

Run:
```bash
venv/bin/python -c "
import structlog, app.main  # configures logging
log = structlog.get_logger('smoke')
log.info('login', password='hunter2', user='ada', ctx={'jwt_kek':'k'})
" 2>&1 | grep -i "REDACTED"
```
Expected: output line shows `password='[REDACTED]'` and `jwt_kek='[REDACTED]'`, `user='ada'` intact.

- [ ] **Step 4: mypy + full existing suite sanity**

Run: `venv/bin/mypy app/main.py app/workers/celery_app.py && venv/bin/pytest tests/core/ -q -k "not observability" 2>&1 | tail -3`
Expected: mypy clean; core suite unaffected (green).

- [ ] **Step 5: Commit**

```bash
git add app/main.py app/workers/celery_app.py
git commit -m "feat(observability): apply secret scrubber to app + worker logging"
```

---

### Task 4: Metrics registry + `/metrics` endpoint + HTTP middleware

**Files:**
- Create: `app/core/observability/metrics.py`
- Modify: `app/main.py` (middleware + `/metrics` route)
- Test: `tests/core/observability/test_metrics.py`

**Interfaces:**
- Consumes: `settings.metrics_enabled` (Task 1).
- Produces:
  - `metrics.py`: `REGISTRY` (a `CollectorRegistry`); `HTTP_REQUESTS` (Counter `sacco_http_requests_total{method,path,status}`), `HTTP_DURATION` (Histogram `sacco_http_request_duration_seconds{method,path}`), `LOGIN_ATTEMPTS` (Counter `sacco_auth_login_attempts_total{outcome,actor_type}`); `render() -> tuple[bytes, str]` returning `(generate_latest(REGISTRY), CONTENT_TYPE_LATEST)`; `record_request(method: str, template: str, status: int, duration_s: float) -> None`.
  - `app/main.py`: an HTTP middleware recording each request under its route template; `GET /metrics` returning the rendered registry (404 when disabled).

- [ ] **Step 1: Write failing tests**

`tests/core/observability/test_metrics.py`:
```python
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.observability import metrics as m


def test_record_request_increments_counter():
    before = m.HTTP_REQUESTS.labels(method="GET", path="/x", status="200")._value.get()
    m.record_request("GET", "/x", 200, 0.01)
    after = m.HTTP_REQUESTS.labels(method="GET", path="/x", status="200")._value.get()
    assert after == before + 1


def test_render_returns_prometheus_payload():
    m.record_request("GET", "/y", 200, 0.02)
    body, content_type = m.render()
    assert b"sacco_http_requests_total" in body
    assert "text/plain" in content_type


@pytest.mark.asyncio
async def test_metrics_endpoint_served(monkeypatch):
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        await c.get("/healthz")
        r = await c.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    assert "sacco_http_requests_total" in r.text
```
(A `metrics_enabled=false → 404` test can be added once the endpoint reads the setting; keep it in this file.)

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/pytest tests/core/observability/test_metrics.py -v`
Expected: FAIL (module + endpoint missing).

- [ ] **Step 3: Implement metrics.py**

```python
"""Prometheus registry + metric objects + a render helper.

Path labels MUST use the matched route template (bounded cardinality),
never the raw request path.
"""
from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

REGISTRY = CollectorRegistry()

HTTP_REQUESTS = Counter(
    "sacco_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
    registry=REGISTRY,
)
HTTP_DURATION = Histogram(
    "sacco_http_request_duration_seconds",
    "HTTP request duration",
    ["method", "path"],
    registry=REGISTRY,
)
LOGIN_ATTEMPTS = Counter(
    "sacco_auth_login_attempts_total",
    "Login attempts",
    ["outcome", "actor_type"],
    registry=REGISTRY,
)


def record_request(method: str, template: str, status: int, duration_s: float) -> None:
    HTTP_REQUESTS.labels(method=method, path=template, status=str(status)).inc()
    HTTP_DURATION.labels(method=method, path=template).observe(duration_s)


def render() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
```

- [ ] **Step 4: Add middleware + endpoint to app/main.py**

Add a metrics middleware (after the existing `request_id_middleware`) and the route. Use the matched route template via `request.scope["route"].path` when present, else a fallback label `"__unmatched__"`:
```python
import time
from fastapi import Response
from app.core.observability import metrics as _metrics


@app.middleware("http")
async def metrics_middleware(request: Request, call_next: Any) -> Any:
    if not settings.metrics_enabled or request.url.path == "/metrics":
        return await call_next(request)
    start = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    template = getattr(route, "path", "__unmatched__")
    _metrics.record_request(
        request.method, template, response.status_code, time.perf_counter() - start
    )
    return response


@app.get("/metrics", tags=["ops"], include_in_schema=False)
async def metrics_endpoint() -> Response:
    if not settings.metrics_enabled:
        return Response(status_code=404)
    body, content_type = _metrics.render()
    return Response(content=body, media_type=content_type)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/pytest tests/core/observability/test_metrics.py -v`
Expected: PASS.

- [ ] **Step 6: mypy + ruff**

Run: `venv/bin/mypy app/core/observability/metrics.py app/main.py && venv/bin/ruff check app/core/observability/`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add app/core/observability/metrics.py app/main.py tests/core/observability/test_metrics.py
git commit -m "feat(observability): /metrics endpoint + HTTP request metrics"
```

---

### Task 5: Business-metric gauges + push + beat task

**Files:**
- Create: `app/core/observability/business_metrics.py`, `app/core/observability/beat.py`
- Modify: `app/workers/celery_app.py` (include + beat_schedule entry)
- Test: `tests/core/observability/test_business_metrics.py`

**Interfaces:**
- Consumes: `settings.pushgateway_url` (Task 1); `platform.tenants`, `platform.subscriptions`, `platform.invoices` (read-only).
- Produces:
  - `business_metrics.py`: `async compute_gauges(session) -> dict[str, dict[tuple, float]]` returning gauge values keyed by metric name → {label-tuple: value}; `build_registry(gauges) -> CollectorRegistry` populating `sacco_tenants_total{status}`, `sacco_subscriptions_total{status}`, `sacco_subscriptions_mrr{currency}`, `sacco_invoices_outstanding{status}`, `sacco_loans_total{status}`; `push(registry, url) -> None` (wraps `push_to_gateway(url, job="sacco-business", registry=...)`). MRR counts only `active`/`trialing` subscriptions.
  - `beat.py`: `emit_business_metrics_gauges()` Celery task — no-op when `pushgateway_url` unset; else compute + push over a platform session.

- [ ] **Step 1: Write failing test for gauge computation**

`tests/core/observability/test_business_metrics.py` (platform-session pattern; seed a tenant + subscription, assert the gauge dict). Mirror the seeding helpers from `tests/platform_/` (async_sessionmaker + commit + cleanup):
```python
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.observability.business_metrics import compute_gauges


@pytest.mark.asyncio
async def test_compute_gauges_counts_tenants_by_status(platform_engine):
    factory = async_sessionmaker(platform_engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        gauges = await compute_gauges(s)
    # tenants gauge is present and keyed by status tuple
    assert "sacco_tenants_total" in gauges
    assert all(isinstance(k, tuple) for k in gauges["sacco_tenants_total"])
```
Add a `tests/core/observability/conftest.py` with a self-contained `platform_engine` fixture:
```python
import os
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine

@pytest_asyncio.fixture
async def platform_engine():
    url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://sacco:sacco@localhost:5433/sacco_test",
    )
    engine = create_async_engine(url)
    yield engine
    await engine.dispose()
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/pytest tests/core/observability/test_business_metrics.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement business_metrics.py**

```python
"""Compute + push business gauges to the Pushgateway (from the beat task).

Workers are separate processes and can't be scraped, so the 60s beat task
pushes a fresh registry each cycle. MRR counts only active/trialing
subscriptions (the dashboard-stats convention).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
from sqlalchemy import func, select, text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_MRR_STATUSES = ("active", "trialing")


async def compute_gauges(session: AsyncSession) -> dict[str, dict[tuple[str, ...], float]]:
    out: dict[str, dict[tuple[str, ...], float]] = {}

    tenants = (
        await session.execute(
            text("SELECT status, count(*) FROM platform.tenants GROUP BY status")
        )
    ).all()
    out["sacco_tenants_total"] = {(str(s),): float(c) for s, c in tenants}

    subs = (
        await session.execute(
            text("SELECT status, count(*) FROM platform.subscriptions GROUP BY status")
        )
    ).all()
    out["sacco_subscriptions_total"] = {(str(s),): float(c) for s, c in subs}

    # MRR: sum of plan base_price for active/trialing subs, per currency.
    mrr = (
        await session.execute(
            text(
                "SELECT p.currency, COALESCE(SUM(p.base_price),0) "
                "FROM platform.subscriptions s "
                "JOIN platform.subscription_plans p ON p.id = s.plan_id "
                "WHERE s.status = ANY(:st) GROUP BY p.currency"
            ),
            {"st": list(_MRR_STATUSES)},
        )
    ).all()
    out["sacco_subscriptions_mrr"] = {(str(cur),): float(v) for cur, v in mrr}

    invoices = (
        await session.execute(
            text("SELECT status, count(*) FROM platform.invoices GROUP BY status")
        )
    ).all()
    out["sacco_invoices_outstanding"] = {(str(s),): float(c) for s, c in invoices}

    return out


def build_registry(gauges: dict[str, dict[tuple[str, ...], float]]) -> CollectorRegistry:
    registry = CollectorRegistry()
    label_names = {
        "sacco_tenants_total": ["status"],
        "sacco_subscriptions_total": ["status"],
        "sacco_subscriptions_mrr": ["currency"],
        "sacco_invoices_outstanding": ["status"],
    }
    for name, values in gauges.items():
        g = Gauge(name, name, label_names[name], registry=registry)
        for label_tuple, value in values.items():
            g.labels(*label_tuple).set(value)
    return registry


def push(registry: CollectorRegistry, url: str) -> None:
    push_to_gateway(url, job="sacco-business", registry=registry)
```
(Verify the exact `platform.invoices` / `subscription_plans` column names against the billing models before running; adjust the SQL if a column differs. `loans` are per-tenant-schema — omit `sacco_loans_total` from v1 gauge push to avoid a cross-schema scan in the 60s task; note it as a Increment-2 follow-up in the module docstring.)

- [ ] **Step 4: Implement the beat task**

`app/core/observability/beat.py`:
```python
"""Celery beat task: push business gauges to the Pushgateway every 60s."""
from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.observability.business_metrics import build_registry, compute_gauges, push
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)


@celery_app.task(name="app.core.observability.beat.emit_business_metrics_gauges")
def emit_business_metrics_gauges() -> None:
    settings = get_settings()
    if not settings.pushgateway_url:
        return
    asyncio.run(_run(settings.database_url, settings.pushgateway_url))


async def _run(database_url: str, pushgateway_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            await session.execute(text("SET LOCAL search_path TO platform"))
            gauges = await compute_gauges(session)
        push(build_registry(gauges), pushgateway_url)
    finally:
        await engine.dispose()
```
In `app/workers/celery_app.py`: add `"app.core.observability.beat"` to `include=[...]` and a `beat_schedule` entry:
```python
        "emit-business-metrics-gauges": {
            "task": "app.core.observability.beat.emit_business_metrics_gauges",
            "schedule": 60.0,
        },
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/pytest tests/core/observability/test_business_metrics.py -v`
Expected: PASS.

- [ ] **Step 6: mypy + ruff**

Run: `venv/bin/mypy app/core/observability/business_metrics.py app/core/observability/beat.py && venv/bin/ruff check app/core/observability/`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add app/core/observability/business_metrics.py app/core/observability/beat.py app/workers/celery_app.py tests/core/observability/test_business_metrics.py tests/core/observability/conftest.py
git commit -m "feat(observability): business gauges pushed to Pushgateway via beat"
```

---

### Task 6: OpenTelemetry tracing scaffold (no-op default)

**Files:**
- Create: `app/core/observability/tracing.py`
- Modify: `app/main.py` (call in lifespan), `app/workers/celery_app.py` (call at bootstrap)
- Test: `tests/core/observability/test_tracing.py`

**Interfaces:**
- Consumes: `settings.otel_exporter_otlp_endpoint` (Task 1).
- Produces: `configure_tracing(app=None) -> bool` — returns `False` and does nothing when the endpoint is unset; else sets up a `TracerProvider` + OTLP exporter, instruments FastAPI (when `app` given), SQLAlchemy, and Celery, and returns `True`.

- [ ] **Step 1: Write failing test**

`tests/core/observability/test_tracing.py`:
```python
from __future__ import annotations

from app.core.observability.tracing import configure_tracing


def test_tracing_is_noop_without_endpoint(monkeypatch):
    monkeypatch.setattr(
        "app.core.observability.tracing.get_settings",
        lambda: _fake(None),
    )
    assert configure_tracing() is False


def test_tracing_configures_with_endpoint(monkeypatch):
    monkeypatch.setattr(
        "app.core.observability.tracing.get_settings",
        lambda: _fake("http://localhost:4317"),
    )
    # No app passed → FastAPI instrumentation skipped; provider still set up.
    assert configure_tracing() is True


class _S:
    def __init__(self, ep): self.otel_exporter_otlp_endpoint = ep


def _fake(ep): return _S(ep)
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/pytest tests/core/observability/test_tracing.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement tracing.py**

```python
"""OpenTelemetry tracing scaffold. No-op unless the OTLP endpoint is set.

configure_tracing() is safe to call from both the FastAPI lifespan and the
Celery bootstrap; when the endpoint env var is unset it returns False and
leaves the process untouched (default dev + all tests).
"""
from __future__ import annotations

from typing import Any

import structlog

from app.core.config import get_settings

_log = structlog.get_logger(__name__)
_configured = False


def configure_tracing(app: Any | None = None) -> bool:
    global _configured
    settings = get_settings()
    endpoint = settings.otel_exporter_otlp_endpoint
    if not endpoint:
        return False
    if _configured:
        if app is not None:
            _instrument_fastapi(app)
        return True

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": "sacco-api"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)

    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.instrumentation.celery import CeleryInstrumentor

    SQLAlchemyInstrumentor().instrument()
    CeleryInstrumentor().instrument()
    if app is not None:
        _instrument_fastapi(app)

    _configured = True
    _log.info("otel.tracing_configured", endpoint=endpoint)
    return True


def _instrument_fastapi(app: Any) -> None:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
```

- [ ] **Step 4: Call it from app + worker (guarded)**

In `app/main.py` lifespan (`async def lifespan`), near startup:
```python
    from app.core.observability.tracing import configure_tracing
    configure_tracing(app)
```
In `app/workers/celery_app.py`, after the app is created:
```python
from app.core.observability.tracing import configure_tracing
configure_tracing()
```

- [ ] **Step 5: Run tests + confirm no-op default doesn't break boot**

Run: `venv/bin/pytest tests/core/observability/test_tracing.py -v && venv/bin/python -c "import app.main; print('boot ok')"`
Expected: tests PASS; `boot ok` printed (tracing no-op, no OTLP endpoint in env).

- [ ] **Step 6: mypy + ruff**

Run: `venv/bin/mypy app/core/observability/tracing.py && venv/bin/ruff check app/core/observability/`
Expected: clean. (If mypy flags the untyped OTEL imports, add targeted `# type: ignore[import-untyped]` and a `[[tool.mypy.overrides]]` module entry for `opentelemetry.*` mirroring the existing jinja2 override.)

- [ ] **Step 7: Commit**

```bash
git add app/core/observability/tracing.py app/main.py app/workers/celery_app.py tests/core/observability/test_tracing.py pyproject.toml
git commit -m "feat(observability): OTEL tracing scaffold (no-op unless configured)"
```

---

### Task 7: Local LGTM stack (compose profile)

**Files:**
- Create: `infra/observability/prometheus/prometheus.yml`, `otel-collector/config.yaml`, `tempo/tempo.yaml`, `loki/loki-config.yaml`, `grafana/provisioning/datasources/datasources.yaml`, `README.md`
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: the API `/metrics` (Task 4), the Pushgateway push (Task 5), OTLP traces (Task 6).
- Produces: an opt-in `observability` profile bringing up prometheus, grafana, tempo, loki, pushgateway, otel-collector; the stack must NOT start on a plain `docker compose up`.

- [ ] **Step 1: Write the config files**

`infra/observability/prometheus/prometheus.yml`:
```yaml
global:
  scrape_interval: 15s
scrape_configs:
  - job_name: sacco-api
    static_configs:
      - targets: ["api:8000"]
  - job_name: pushgateway
    honor_labels: true
    static_configs:
      - targets: ["pushgateway:9091"]
```
`infra/observability/otel-collector/config.yaml`:
```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
exporters:
  otlp/tempo:
    endpoint: tempo:4317
    tls:
      insecure: true
service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [otlp/tempo]
```
`infra/observability/tempo/tempo.yaml` (minimal single-binary), `infra/observability/loki/loki-config.yaml` (minimal single-binary) — use the upstream example single-binary configs.
`infra/observability/grafana/provisioning/datasources/datasources.yaml`:
```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    url: http://prometheus:9090
    access: proxy
  - name: Tempo
    type: tempo
    url: http://tempo:3200
    access: proxy
  - name: Loki
    type: loki
    url: http://loki:3100
    access: proxy
```
`infra/observability/README.md`: how to run (`docker compose --profile observability up`), where each UI lives (Grafana :3001, Prometheus :9090), the verify steps, and the prod-swap note (point `otel_exporter_otlp_endpoint` + `pushgateway_url` at managed collectors).

- [ ] **Step 2: Add profiled services to compose**

Add to `docker-compose.yml` (all with `profiles: ["observability"]`, on `sacco_net`, with named volumes as needed):
```yaml
  prometheus:
    image: prom/prometheus:latest
    profiles: ["observability"]
    networks: [sacco_net]
    volumes:
      - ./infra/observability/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    ports: ["9090:9090"]
  pushgateway:
    image: prom/pushgateway:latest
    profiles: ["observability"]
    networks: [sacco_net]
    ports: ["9091:9091"]
  tempo:
    image: grafana/tempo:latest
    profiles: ["observability"]
    networks: [sacco_net]
    command: ["-config.file=/etc/tempo/tempo.yaml"]
    volumes:
      - ./infra/observability/tempo/tempo.yaml:/etc/tempo/tempo.yaml:ro
  loki:
    image: grafana/loki:latest
    profiles: ["observability"]
    networks: [sacco_net]
    command: ["-config.file=/etc/loki/loki-config.yaml"]
    volumes:
      - ./infra/observability/loki/loki-config.yaml:/etc/loki/loki-config.yaml:ro
  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    profiles: ["observability"]
    networks: [sacco_net]
    command: ["--config=/etc/otel/config.yaml"]
    volumes:
      - ./infra/observability/otel-collector/config.yaml:/etc/otel/config.yaml:ro
    ports: ["4317:4317"]
  grafana:
    image: grafana/grafana:latest
    profiles: ["observability"]
    networks: [sacco_net]
    environment:
      GF_AUTH_ANONYMOUS_ENABLED: "true"
      GF_AUTH_ANONYMOUS_ORG_ROLE: Admin
    volumes:
      - ./infra/observability/grafana/provisioning:/etc/grafana/provisioning:ro
    ports: ["3001:3000"]
```

- [ ] **Step 3: Verify the profile is opt-in**

Run:
```bash
docker compose config --services | sort > /tmp/default-svcs.txt
docker compose --profile observability config --services | sort > /tmp/obs-svcs.txt
grep -qx prometheus /tmp/default-svcs.txt && echo "BUG: prometheus in default" || echo "OK: opt-in"
diff /tmp/default-svcs.txt /tmp/obs-svcs.txt | grep -E "prometheus|grafana|tempo|loki|pushgateway|otel-collector"
```
Expected: `OK: opt-in`; the six services appear only in the profile list.

- [ ] **Step 4: Bring the stack up + smoke Prometheus scrape**

Run (API must be running with `metrics_enabled=true`, `otel_exporter_otlp_endpoint=http://otel-collector:4317`, `pushgateway_url=http://pushgateway:9091` in its env):
```bash
docker compose --profile observability up -d prometheus pushgateway tempo loki otel-collector grafana
sleep 20
curl -s "http://localhost:9090/api/v1/query?query=sacco_http_requests_total" | grep -o '"status":"success"'
```
Expected: `"status":"success"` (Prometheus reachable; metric present once the API has served a request — hit `curl localhost:8000/healthz` a few times first).

- [ ] **Step 5: Commit**

```bash
git add infra/observability/ docker-compose.yml
git commit -m "feat(observability): local LGTM stack under an opt-in compose profile"
```

---

### Task 8: Close-out — CLAUDE.md + full gates + verification note

**Files:**
- Modify: `CLAUDE.md`
- Create: `infra/observability/VERIFICATION.md` (the end-to-end proof note)

- [ ] **Step 1: Run the full backend gates**

Run:
```bash
venv/bin/ruff check app/core/observability/ && venv/bin/mypy app/core/observability/ app/main.py app/workers/celery_app.py
venv/bin/pytest tests/core/observability/ -q
venv/bin/pytest tests/core/ -q 2>&1 | tail -3
```
Expected: ruff + mypy clean; observability suite green; core suite unaffected.

- [ ] **Step 2: Capture the end-to-end verification note**

Bring up the API + worker + observability profile, drive a few routes, wait one beat cycle, and record in `infra/observability/VERIFICATION.md`: the Prometheus query showing `sacco_http_requests_total`, the Pushgateway page showing `sacco_tenants_total`, and a Tempo trace id for a request. Paste the commands + trimmed outputs.

- [ ] **Step 3: Update CLAUDE.md**

- Roadmap table row 5 (Observability): status → **In progress — increment 1**.
- Add an **Observability contracts (Phase 5 — do not violate)** subsection:
  - All observability code lives in `app/core/observability/`.
  - The secret-scrubbing processor (`make_scrub_processor`) is mandatory in every logging config — app (`app/main.py`) AND worker (`app/workers/celery_app.py`). Adding a log config without it is a violation.
  - `/metrics` is unauthenticated and NOT subscription-gated (Prometheus scrapes it); internal-network-only in production; 404 when `metrics_enabled=false`. Metric path labels use the route template, never the raw path.
  - Tracing is a no-op unless `otel_exporter_otlp_endpoint` is set; `configure_tracing()` is safe to call unconditionally.
  - Business gauges are PUSHED from the `emit_business_metrics_gauges` beat task to the Pushgateway (workers can't be scraped); MRR counts only `active`/`trialing`. Never scrape workers directly.
  - The LGTM stack is opt-in via the `observability` compose profile; it must not start on a plain `docker compose up`.
  - Increment 2 (dashboards, Alertmanager, alert runbooks, Loki shipping) is pending.
- Add a one-line scope-exception note near contract N (edits compose, adds `infra/observability/` + `app/core/observability/` + pyproject deps).

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md infra/observability/VERIFICATION.md
git commit -m "docs(claude): observability contracts + increment-1 verification"
```

## Out of scope (Increment 2 — reminder)

- The 8 Grafana dashboard JSONs, Alertmanager + alert catalogue, per-alert runbooks.
- Loki log shipping (Promtail / collector filelog receiver) so JSON logs land in Loki.
- `docs/observability-runbook.md`, `docs/metrics-catalogue.md`.
- Datadog / Grafana Cloud alternatives; sampling tuning; per-endpoint SLOs.
