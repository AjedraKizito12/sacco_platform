# Phase 5 — Observability & Monitoring (Logfire) Implementation Plan

> ⚠️ **SECURITY ERRATUM (post-implementation, do not re-implement the old design).**
> This plan's original scrubbing design used a `logfire.ScrubbingOptions(callback=...)`
> that returned `match.value` for keys outside the project keyset. That is a
> vulnerability: Logfire's callback *un-redacts* any value it returns, so returning
> `match.value` **disables** Logfire's built-in secret scrubbing (cookie/jwt/
> authorization/api_key/…). The shipped implementation instead uses
> `ScrubbingOptions(extra_patterns=SCRUB_EXTRA_PATTERNS)` (Logfire defaults ∪ project
> patterns) with NO value-returning callback, plus a `server_request_hook` +
> `request_attributes_mapper=None` to strip URL-query / endpoint-argument PII that
> Logfire's SAFE_KEYS otherwise bypass. See the "Observability contracts" section of
> `CLAUDE.md`, `docs/observability-runbook.md`, and the fix in the final commit.
> Ignore the callback-based scrubbing described in the task bodies below.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship structured logs, distributed traces, and business metrics to Pydantic Logfire from the FastAPI API and Celery workers, with a strict metadata-only egress posture, plus dashboards, alerts, and runbooks.

**Architecture:** A focused `app/core/observability/` library configures Logfire once at process start (API lifespan + Celery worker init), auto-instruments FastAPI/SQLAlchemy/Celery/Redis/HTTPX, scrubs secrets and PII before egress, and binds tenant/actor context onto spans. A Celery beat task emits business gauges. Dashboards and alerts live in Logfire (managed via the Logfire MCP), not in the admin portal.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 async, Celery, structlog, `logfire` SDK (OpenTelemetry under the hood), pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-08-01-observability-logfire-design.md`

## Global Constraints

- **Egress posture is strict / metadata-only.** SQL bind-parameter capture OFF; FastAPI request/response body capture OFF; secrets + PII scrubbed. Monetary amounts are intentionally NOT scrubbed.
- **Scrub keyset (single source of truth in `app/core/observability/scrubbing.py`):** `password`, `token`, `secret`, `jwt_kek`, `hashed_password`, `national_id_number`, `email`, `phone`, `first_name`, `last_name`, `dob`. Case-insensitive.
- **`send_to_logfire` gating:** `True` only when `LOGFIRE_TOKEN` is set; `False` when token absent and `APP_ENV != production`; **always `False` under tests** (`APP_ENV=test` or pytest detected). No telemetry leaves in CI/dev.
- **`configure_observability()` is the ONLY place `logfire.configure()` is called.** It is idempotent.
- **No changes to `admin/`, `alembic/`, or any financial/business-logic behaviour.** Spans and counters wrap existing calls; they never change outcomes.
- **Metric names prefixed `sacco_`; labels are statuses/ids/currencies only — never PII.** MRR counts `active` + `trialing` subscriptions only (matches the dashboard-stats contract).
- **Money:** integer minor units or DECIMAL(19,4); never float. **Async everywhere; no sync DB code.**
- **ruff + mypy (strict) must stay clean.** Add deps only with commit-message justification.
- Tests: `pytest` from repo root (`asyncio_mode = "auto"` already set). Existing structlog config in `app/main.py::_configure_logging()` is KEPT — we bridge to it, not replace it.

---

## File Structure

```
app/core/observability/
  __init__.py        public surface: configure_observability(), bind_actor_context(), business metric handles
  config.py          ObservabilityConfig: token/environment/service resolution + send_to_logfire gating
  scrubbing.py       SCRUB_KEYS + scrubbing_callback() (single source of truth)
  logging.py         structlog processor that scrubs event dicts; wiring notes for the existing config
  instrument.py      instrument_all(app=None): FastAPI + SQLAlchemy + Celery + Redis + HTTPX, bind/body/param flags
  context.py         bind_actor_context(**kw): structlog contextvars + current-span attributes
  metrics.py         (Inc 2) business metric instruments + record_business_gauges()
tests/core/observability/
  test_config.py, test_scrubbing.py, test_context.py, test_metrics.py, test_instrument_smoke.py
```

Modified: `app/main.py` (call configure + instrument in lifespan; enhance `/readyz`; swap the 6 `bind_contextvars` auth-dep sites to `bind_actor_context`), `app/workers/celery_app.py` (configure + instrument on worker init; add beat entry), `app/core/observability/*` new, `pyproject.toml` (add `logfire` extras), `docker-compose.yml` + `docker-compose.staging.yml` (env only), `docs/*`, `CLAUDE.md` (close-out).

---

## Increment 1 — Foundation

### Task 1: Add the `logfire` dependency + config surface

**Files:**
- Modify: `pyproject.toml` (dependencies list, after `structlog==24.4.0`)
- Create: `app/core/observability/__init__.py`
- Create: `app/core/observability/config.py`
- Test: `tests/core/observability/__init__.py`, `tests/core/observability/test_config.py`

**Interfaces:**
- Produces: `ObservabilityConfig` (dataclass: `token: str | None`, `environment: str`, `service: str`, `send_to_logfire: bool`); `resolve_config(service: str) -> ObservabilityConfig`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/observability/test_config.py
import pytest
from app.core.observability.config import resolve_config


def test_no_token_non_prod_disables_egress(monkeypatch):
    monkeypatch.delenv("LOGFIRE_TOKEN", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    cfg = resolve_config(service="api")
    assert cfg.send_to_logfire is False
    assert cfg.service == "api"
    assert cfg.environment == "development"


def test_token_enables_egress(monkeypatch):
    monkeypatch.setenv("LOGFIRE_TOKEN", "pylf_test")
    monkeypatch.setenv("APP_ENV", "staging")
    cfg = resolve_config(service="worker")
    assert cfg.send_to_logfire is True


def test_tests_env_always_disables_egress(monkeypatch):
    # Even with a token, APP_ENV=test must never ship telemetry.
    monkeypatch.setenv("LOGFIRE_TOKEN", "pylf_test")
    monkeypatch.setenv("APP_ENV", "test")
    cfg = resolve_config(service="api")
    assert cfg.send_to_logfire is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/observability/test_config.py -v`
Expected: FAIL (module `app.core.observability.config` not found)

- [ ] **Step 3: Add the dependency**

In `pyproject.toml` dependencies, add:
```
    "logfire[fastapi,sqlalchemy,celery,redis,httpx]==3.14.0",
```
(Pin the currently-resolved version; verify with `pip index versions logfire` or accept the lockfile's resolution. The extras pull the OTel instrumentation packages.)

- [ ] **Step 4: Write `config.py`**

```python
# app/core/observability/config.py
from __future__ import annotations

import os
from dataclasses import dataclass

from app.core.config import get_settings


@dataclass(frozen=True)
class ObservabilityConfig:
    token: str | None
    environment: str
    service: str
    send_to_logfire: bool


def _is_test_env(environment: str) -> bool:
    return environment == "test" or "PYTEST_CURRENT_TEST" in os.environ


def resolve_config(service: str) -> ObservabilityConfig:
    settings = get_settings()
    environment = settings.app_env
    token = os.environ.get("LOGFIRE_TOKEN") or None
    if _is_test_env(environment):
        send = False
    else:
        send = token is not None
    return ObservabilityConfig(
        token=token, environment=environment, service=service, send_to_logfire=send
    )
```

Leave `__init__.py` empty for now (public exports added in later tasks).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/core/observability/test_config.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml app/core/observability/ tests/core/observability/
git commit -m "feat(observability): logfire dep + config surface with egress gating"
```

---

### Task 2: Scrubbing keyset + callback

**Files:**
- Create: `app/core/observability/scrubbing.py`
- Create: `app/core/observability/logging.py`
- Test: `tests/core/observability/test_scrubbing.py`

**Interfaces:**
- Produces: `SCRUB_KEYS: frozenset[str]`; `scrubbing_callback(match) -> Any` (Logfire `ScrubbingOptions.callback` shape — returns `None`/redaction to scrub); `should_scrub(key: str) -> bool`; `scrub_event_dict(logger, method, event_dict) -> dict` (structlog processor).

- [ ] **Step 1: Write the failing test**

```python
# tests/core/observability/test_scrubbing.py
from app.core.observability.scrubbing import (
    SCRUB_KEYS, should_scrub, scrub_event_dict,
)


def test_keyset_covers_secrets_and_pii():
    for k in ("password", "jwt_kek", "hashed_password", "national_id_number",
              "email", "phone", "first_name", "last_name", "dob", "token", "secret"):
        assert k in SCRUB_KEYS


def test_amount_is_not_scrubbed():
    assert should_scrub("amount") is False
    assert should_scrub("total_amount") is False


def test_should_scrub_case_insensitive_and_substring():
    assert should_scrub("Email") is True
    assert should_scrub("user_password") is True


def test_scrub_event_dict_redacts_pii_keeps_amount():
    out = scrub_event_dict(None, "info", {
        "event": "loan repaid", "amount": 5000, "email": "a@b.com",
        "hashed_password": "x", "loan_id": "L-1",
    })
    assert out["amount"] == 5000
    assert out["loan_id"] == "L-1"
    assert out["email"] == "[scrubbed]"
    assert out["hashed_password"] == "[scrubbed]"
    assert out["event"] == "loan repaid"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/observability/test_scrubbing.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Write `scrubbing.py`**

```python
# app/core/observability/scrubbing.py
from __future__ import annotations

from typing import Any

SCRUB_KEYS: frozenset[str] = frozenset({
    "password", "token", "secret", "jwt_kek", "hashed_password",
    "national_id_number", "email", "phone", "first_name", "last_name", "dob",
})

_REDACTION = "[scrubbed]"


def should_scrub(key: str) -> bool:
    lowered = key.lower()
    return any(candidate in lowered for candidate in SCRUB_KEYS)


def scrub_event_dict(logger: Any, method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor: redact any key whose name matches the scrub keyset."""
    for key in list(event_dict.keys()):
        if key == "event":
            continue
        if should_scrub(key):
            event_dict[key] = _REDACTION
    return event_dict


def scrubbing_callback(match: Any) -> Any:
    """Logfire ScrubbingOptions callback. Return None to redact.

    Logfire calls this for every value whose path matches its own patterns;
    we additionally redact anything matching our keyset by path key name.
    """
    path_keys = [str(p) for p in getattr(match, "path", [])]
    if any(should_scrub(k) for k in path_keys):
        return None
    return match.value
```

- [ ] **Step 4: Write `logging.py`**

```python
# app/core/observability/logging.py
from __future__ import annotations

from app.core.observability.scrubbing import scrub_event_dict

# The existing structlog config lives in app.main._configure_logging().
# Task 3 inserts `scrub_event_dict` into that processor chain (before the
# renderer) and appends the Logfire structlog processor so log records with
# scrubbed keys become Logfire log records. This module re-exports the
# processor so main.py imports from one place.

__all__ = ["scrub_event_dict"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/core/observability/test_scrubbing.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add app/core/observability/scrubbing.py app/core/observability/logging.py tests/core/observability/test_scrubbing.py
git commit -m "feat(observability): scrub keyset + structlog/logfire scrubbing callbacks"
```

---

### Task 3: `configure_observability()` + instrumentation wiring

**Files:**
- Create: `app/core/observability/instrument.py`
- Modify: `app/core/observability/__init__.py`
- Test: `tests/core/observability/test_instrument_smoke.py`

**Interfaces:**
- Consumes: `resolve_config` (Task 1), `scrubbing_callback` + `scrub_event_dict` (Task 2).
- Produces: `configure_observability(service: str, app=None) -> None` (idempotent; configures Logfire with scrubbing + `send_to_logfire`, then calls `instrument_all`); `instrument_all(app=None) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/observability/test_instrument_smoke.py
import logfire
from app.core.observability import configure_observability


def test_configure_is_idempotent_and_offline_under_tests(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LOGFIRE_TOKEN", "pylf_test")  # must still be offline
    # Should not raise, and calling twice is safe.
    configure_observability(service="api")
    configure_observability(service="api")
    # A span works without shipping anywhere.
    with logfire.span("smoke"):
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/observability/test_instrument_smoke.py -v`
Expected: FAIL (`configure_observability` not importable from package)

- [ ] **Step 3: Write `instrument.py`**

```python
# app/core/observability/instrument.py
from __future__ import annotations

import logfire

from app.core.observability.config import resolve_config
from app.core.observability.scrubbing import scrubbing_callback

_configured = False


def configure_observability(service: str, app: object | None = None) -> None:
    global _configured
    cfg = resolve_config(service=service)
    if not _configured:
        logfire.configure(
            service_name=f"sacco-{service}",
            environment=cfg.environment,
            token=cfg.token,
            send_to_logfire=cfg.send_to_logfire,
            scrubbing=logfire.ScrubbingOptions(callback=scrubbing_callback),
            console=False if cfg.send_to_logfire else None,
        )
        _configured = True
    instrument_all(app=app)


def instrument_all(app: object | None = None) -> None:
    # SQL: statement shape only — never bind parameters.
    logfire.instrument_sqlalchemy(enable_commenter=False)
    logfire.instrument_redis()
    logfire.instrument_httpx()
    logfire.instrument_celery()
    if app is not None:
        # capture_headers stays default-off; bodies not captured.
        logfire.instrument_fastapi(app, capture_headers=False)
```

Note for implementer: confirm the exact kwarg names against the pinned
`logfire` version (`instrument_sqlalchemy` param for suppressing bind params
may be named differently across versions — the requirement is *no bind
parameters leave the process*; verify by asserting in Task 3's follow-up or
Task 4). If a kwarg differs, adjust and keep the no-bind-param guarantee.

- [ ] **Step 4: Update `__init__.py`**

```python
# app/core/observability/__init__.py
from app.core.observability.instrument import (
    configure_observability,
    instrument_all,
)

__all__ = ["configure_observability", "instrument_all"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/core/observability/test_instrument_smoke.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/core/observability/instrument.py app/core/observability/__init__.py tests/core/observability/test_instrument_smoke.py
git commit -m "feat(observability): configure_observability + auto-instrumentation"
```

---

### Task 4: Tenant/actor span context + scrubbing enforcement test

**Files:**
- Create: `app/core/observability/context.py`
- Modify: `app/core/observability/__init__.py`
- Test: `tests/core/observability/test_context.py`

**Interfaces:**
- Produces: `bind_actor_context(**kwargs: str) -> None` — binds structlog contextvars (unchanged behaviour) AND sets the same keys as attributes on the current OTel/Logfire span.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/observability/test_context.py
import logfire
import structlog
from app.core.observability import configure_observability
from app.core.observability.context import bind_actor_context


def test_bind_actor_context_sets_structlog_and_span(monkeypatch, capfd):
    monkeypatch.setenv("APP_ENV", "test")
    configure_observability(service="api")
    structlog.contextvars.clear_contextvars()
    with logfire.span("req") as span:
        bind_actor_context(
            actor_type="tenant_user", actor_id="00000000-0000-0000-0000-000000000001",
            tenant_schema="tenant_acme",
        )
        attrs = span.attributes or {}
        assert attrs.get("actor_type") == "tenant_user"
        assert attrs.get("tenant_schema") == "tenant_acme"
    # structlog contextvars also carry it
    ctx = structlog.contextvars.get_contextvars()
    assert ctx["actor_type"] == "tenant_user"
```

(If `span.attributes` is not directly readable on the pinned SDK, assert via a
local in-memory span exporter fixture instead — the requirement is that the
attributes land on the active span.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/observability/test_context.py -v`
Expected: FAIL (`context` module not found)

- [ ] **Step 3: Write `context.py`**

```python
# app/core/observability/context.py
from __future__ import annotations

import structlog
from opentelemetry import trace


def bind_actor_context(**kwargs: str) -> None:
    """Bind actor/tenant identifiers to both the structlog contextvars and the
    current span. Ids/labels only — never PII. This is the single wrapper the
    auth deps call in place of a bare structlog.contextvars.bind_contextvars.
    """
    structlog.contextvars.bind_contextvars(**kwargs)
    span = trace.get_current_span()
    if span is not None and span.is_recording():
        for key, value in kwargs.items():
            span.set_attribute(key, value)
```

- [ ] **Step 4: Export it**

Add `bind_actor_context` to `app/core/observability/__init__.py` `__all__` and imports.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/core/observability/test_context.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/core/observability/context.py app/core/observability/__init__.py tests/core/observability/test_context.py
git commit -m "feat(observability): bind actor/tenant context to spans + contextvars"
```

---

### Task 5: Wire into the API (`app/main.py`) + `/readyz` latency

**Files:**
- Modify: `app/main.py` (lifespan configure+instrument; processor chain; `/readyz`; swap `bind_contextvars` sites)
- Modify: `app/modules/iam/dependencies.py` (3 `bind_contextvars` sites → `bind_actor_context`)
- Modify: `app/platform_/auth.py` (1 `bind_contextvars` site → `bind_actor_context`)
- Test: `tests/test_readyz_latency.py`

**Interfaces:**
- Consumes: `configure_observability`, `bind_actor_context`, `scrub_event_dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_readyz_latency.py
from httpx import ASGITransport, AsyncClient
from app.main import app


async def test_readyz_includes_per_dependency_latency():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.get("/readyz")
    body = resp.json()
    assert "checks" in body
    # each check now reports {status, latency_ms}
    for name, check in body["checks"].items():
        assert "status" in check
        assert "latency_ms" in check
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_readyz_latency.py -v`
Expected: FAIL (checks are bare strings, no `latency_ms`)

- [ ] **Step 3: Enhance `/readyz`**

Change each `_check_*` helper to time itself and return `dict[str, object]`:
```python
async def _check_postgres() -> dict[str, object]:
    import time
    from sqlalchemy import text
    start = time.perf_counter()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        status = "ok"
    except Exception as exc:
        status = f"error: {exc}"
    return {"status": status, "latency_ms": round((time.perf_counter() - start) * 1000, 1)}
```
Apply the same shape to `_check_redis`, `_check_rabbitmq`, `_check_elasticsearch`. Update `readyz` to compute `all_ok` from `check["status"] == "ok"`.

- [ ] **Step 4: Wire configure + instrument + scrubbing processor**

In `app/main.py`:
- In `_configure_logging()`, insert `scrub_event_dict` into `processors` immediately before the renderer append, and (only when shipping) append the Logfire structlog processor. Import: `from app.core.observability.logging import scrub_event_dict`.
- In `lifespan`, at the top of the function body, call:
  ```python
  from app.core.observability import configure_observability
  configure_observability(service="api", app=app)
  ```
- Replace the 6 `structlog.contextvars.bind_contextvars(...)` auth sites (in `app/modules/iam/dependencies.py` lines ~100/153/226/257/319 and `app/platform_/auth.py` line ~77) with `bind_actor_context(...)` (same kwargs). Import `from app.core.observability import bind_actor_context`. Leave the `request_id_middleware` bind as-is (request_id is not actor context; it already flows via merge_contextvars).

- [ ] **Step 5: Run the full suite + gates**

Run: `pytest tests/test_readyz_latency.py tests/core/observability -v && ruff check app/ && mypy app/core/observability app/main.py`
Expected: PASS + clean

- [ ] **Step 6: Manual proof (record in commit body)**

Run: `docker compose up -d api` then `curl -s localhost:8000/readyz | jq` — confirm each check has `latency_ms`. With `LOGFIRE_TOKEN` unset, confirm the API logs render to console and no egress occurs (dev). Optionally set a real token in a scratch env and confirm one trace lands in Logfire with `tenant_schema`/`actor_type` attributes and NO bind params / PII (query via the Logfire MCP `query_run`).

- [ ] **Step 7: Commit**

```bash
git add app/main.py app/modules/iam/dependencies.py app/platform_/auth.py tests/test_readyz_latency.py
git commit -m "feat(observability): wire Logfire into API lifespan, /readyz latency, actor context"
```

---

### Task 6: Wire into Celery workers

**Files:**
- Modify: `app/workers/celery_app.py`
- Test: `tests/workers/test_worker_observability_init.py`

**Interfaces:**
- Consumes: `configure_observability`.

- [ ] **Step 1: Write the failing test**

```python
# tests/workers/test_worker_observability_init.py
from unittest.mock import patch
from app.workers import celery_app as celery_mod


def test_worker_init_configures_observability(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    with patch("app.core.observability.configure_observability") as cfg:
        celery_mod._init_observability()  # signal handler body, extracted for testability
        cfg.assert_called_once()
        assert cfg.call_args.kwargs["service"] in {"worker", "beat"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/workers/test_worker_observability_init.py -v`
Expected: FAIL (`_init_observability` not defined)

- [ ] **Step 3: Add worker init hook**

In `app/workers/celery_app.py`, after `celery_app` is built:
```python
import os
from celery.signals import worker_process_init, beat_init


def _init_observability(service: str | None = None) -> None:
    from app.core.observability import configure_observability
    svc = service or ("beat" if os.environ.get("SACCO_BEAT") else "worker")
    configure_observability(service=svc)


@worker_process_init.connect
def _on_worker_init(**_: object) -> None:
    _init_observability(service="worker")


@beat_init.connect
def _on_beat_init(**_: object) -> None:
    _init_observability(service="beat")
```
(`logfire.instrument_celery()` inside `configure_observability` creates task spans; no per-task change needed.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/workers/test_worker_observability_init.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/workers/celery_app.py tests/workers/test_worker_observability_init.py
git commit -m "feat(observability): configure Logfire on Celery worker + beat init"
```

---

### Task 7: Compose env + Increment-1 close (docs stub)

**Files:**
- Modify: `docker-compose.yml`, `docker-compose.staging.yml` (env passthrough only)
- Create: `docs/observability-runbook.md` (initial: setup + scrub policy)

- [ ] **Step 1: Add env passthrough**

In `docker-compose.yml` and `docker-compose.staging.yml`, add to the `api`, `worker`/`beat` service `environment:` blocks:
```yaml
      LOGFIRE_TOKEN: ${LOGFIRE_TOKEN:-}
      APP_ENV: ${APP_ENV:-development}
```
(Staging already sources `.env.staging`; document `LOGFIRE_TOKEN` in `.env.staging.example`.)

- [ ] **Step 2: Write the runbook stub**

`docs/observability-runbook.md` covering: what Logfire is, the `send_to_logfire` gating table, the scrub keyset + policy (amounts NOT scrubbed; bind params/bodies off), how to set `LOGFIRE_TOKEN` per environment, and "how to add a metric/dashboard/alert" (filled in Inc 2/3).

- [ ] **Step 3: Verify gates**

Run: `docker compose config -q && ruff check app/ && mypy app/`
Expected: clean

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml docker-compose.staging.yml .env.staging.example docs/observability-runbook.md
git commit -m "feat(observability): compose env passthrough + runbook stub (Inc 1 complete)"
```

---

## Increment 2 — Business metrics & custom spans

### Task 8: Business metric instruments + `emit_business_metrics_gauges` beat

**Files:**
- Create: `app/core/observability/metrics.py`
- Create: `app/core/observability/beat.py`
- Modify: `app/workers/celery_app.py` (add `include` entry + `beat_schedule` entry)
- Test: `tests/core/observability/test_metrics.py`

**Interfaces:**
- Produces: gauge handles in `metrics.py`; `record_business_gauges(session_factory) -> None` (async) computing and setting each gauge; Celery task `emit_business_metrics_gauges`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/observability/test_metrics.py
import pytest
from app.core.observability.metrics import compute_business_gauges


@pytest.mark.asyncio
async def test_compute_business_gauges_shapes(platform_session_factory):
    # platform_session_factory: existing fixture pattern (async_sessionmaker + commit)
    result = await compute_business_gauges(platform_session_factory)
    # returns a dict of metric-name -> list[(labels, value)]
    assert "sacco_tenants_total" in result
    assert "sacco_subscriptions_mrr" in result
    # MRR only counts active + trialing (contract)
    assert all(isinstance(v, (int, float)) for _, v in result["sacco_subscriptions_mrr"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/observability/test_metrics.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Write `metrics.py`**

Define OTel gauges via `logfire.metric_gauge(...)` for: `sacco_tenants_total{status}`, `sacco_subscriptions_total{status}`, `sacco_subscriptions_mrr{currency}` (WHERE status IN ('active','trialing')), `sacco_invoices_outstanding{status}`, `sacco_loans_total{status}` (summed across tenant schemas), `sacco_outbox_queue_depth{schema}` (unpublished rows per schema), `sacco_backup_age_seconds` (from `platform.backup_runs` latest succeeded `finished_at`). `compute_business_gauges(session_factory)` runs the read-only SQL and returns the `{name: [(labels, value)]}` map; `record_business_gauges` sets each gauge. All queries are async, read-only, and never touch financial tables for writes.

- [ ] **Step 4: Write the beat task**

```python
# app/core/observability/beat.py
from __future__ import annotations

import asyncio
import structlog
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)


@celery_app.task(name="app.core.observability.beat.emit_business_metrics_gauges")
def emit_business_metrics_gauges() -> None:
    from app.core.observability.metrics import record_business_gauges
    asyncio.run(record_business_gauges())
```

- [ ] **Step 5: Register in Celery**

Add `"app.core.observability.beat"` to the `include=[...]` list and a `beat_schedule` entry:
```python
        "emit-business-metrics-gauges": {
            "task": "app.core.observability.beat.emit_business_metrics_gauges",
            "schedule": 60.0,
        },
```

- [ ] **Step 6: Run tests + gates**

Run: `pytest tests/core/observability/test_metrics.py -v && ruff check app/ && mypy app/core/observability`
Expected: PASS + clean

- [ ] **Step 7: Commit**

```bash
git add app/core/observability/metrics.py app/core/observability/beat.py app/workers/celery_app.py tests/core/observability/test_metrics.py
git commit -m "feat(observability): business metric gauges + emit_business_metrics_gauges beat"
```

---

### Task 9: Custom spans/counters on key flows

**Files:**
- Modify: `app/core/outbox/worker.py` (publish-latency span + dead-letter counter)
- Modify: `app/modules/maker_checker/service.py` (approval decision counter, self-reject counter)
- Modify: `app/modules/reporting/beat.py` (materialization duration + last-run gauge)
- Modify: one auth login path each (`PlatformAuthService.login`, `TenantAuthService.login`) — login-attempt counter `{outcome,actor_type}`
- Test: `tests/core/observability/test_custom_spans.py`

**Interfaces:**
- Consumes: metric handles from Task 8 (add counters/histograms there: `sacco_outbox_publish_duration_seconds`, `sacco_outbox_dead_lettered_total`, `sacco_auth_login_attempts_total`, `sacco_report_materialize_duration_seconds`, `sacco_report_last_run_timestamp`).

- [ ] **Step 1: Add the metric handles**

In `metrics.py`, add the counter/histogram handles listed above via `logfire.metric_counter(...)` / `logfire.metric_histogram(...)`. Labels: statuses/outcomes/types only.

- [ ] **Step 2: Write the failing test**

```python
# tests/core/observability/test_custom_spans.py
from app.core.observability import metrics


def test_login_counter_handle_exists():
    assert hasattr(metrics, "auth_login_attempts")
    # increment with a label set does not raise
    metrics.auth_login_attempts.add(1, {"outcome": "success", "actor_type": "tenant_user"})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/core/observability/test_custom_spans.py -v`
Expected: FAIL (handle missing)

- [ ] **Step 4: Wire the increments**

At each call site, wrap with a thin `with logfire.span(...)` or increment the counter — NO behaviour change. Example (outbox publish):
```python
import time
from app.core.observability import metrics
start = time.perf_counter()
# ... existing publish ...
metrics.outbox_publish_duration.record(time.perf_counter() - start)
```
Login paths: increment `auth_login_attempts` with `{"outcome": "success"|"invalid_credentials"|"locked", "actor_type": ...}` on each branch. Keep the existing audit writes untouched.

- [ ] **Step 5: Run tests + gates**

Run: `pytest tests/core/observability -v && ruff check app/ && mypy app/`
Expected: PASS + clean

- [ ] **Step 6: Commit**

```bash
git add app/core/observability/metrics.py app/core/outbox/worker.py app/modules/maker_checker/service.py app/modules/reporting/beat.py app/modules/iam/ tests/core/observability/test_custom_spans.py
git commit -m "feat(observability): custom spans + counters on outbox, maker-checker, reporting, auth (Inc 2 complete)"
```

---

## Increment 3 — Dashboards, alerts, runbooks

### Task 10: Logfire dashboards (via MCP) + committed JSON

**Files:**
- Create: `infra/observability/logfire/dashboards/` (exported JSON per dashboard, where the Logfire API supports export)
- Modify: `docs/observability-runbook.md` (dashboard section)

- [ ] **Step 1: Create dashboards via the Logfire MCP**

Using the Logfire MCP `dashboard_create` / `dashboard_add_panel` tools, build: Platform overview (req rate, 5xx %, p50/95/99 latency, active tenants/sessions), Billing (subs by status, MRR, overdue invoices), Maker-checker, Outbox, Reporting, Background jobs, Database, Tenant drilldown. Panels query the `sacco_*` metrics + trace data.

- [ ] **Step 2: Export + commit JSON**

For each dashboard, `dashboard_get` and save the definition under `infra/observability/logfire/dashboards/<name>.json`. Document in the runbook that these are reproducibility snapshots (source of truth is the Logfire project).

- [ ] **Step 3: Commit**

```bash
git add infra/observability/logfire/dashboards/ docs/observability-runbook.md
git commit -m "feat(observability): Logfire dashboards + committed JSON snapshots"
```

---

### Task 11: Alerts (email-only) + alert runbooks + CLAUDE.md close-out

**Files:**
- Create: `docs/alert-runbooks/` (one MD per alert)
- Create: `docs/metrics-catalogue.md`
- Modify: `docs/observability-runbook.md` (alerts section)
- Modify: `CLAUDE.md` (roadmap row 5 → Done; Observability contracts section; Phase 5 note under contract N)

- [ ] **Step 1: Create the email channel + alerts via MCP**

Create an email notification channel, then SQL-based alerts:
- *Critical:* API error rate >5%/5min; p99 latency >5s/10min; outbox dead-letter grew this hour; any beat task missed 2× schedule; `/readyz` 503 >2min; backup age >36h.
- *Warning:* approvals pending >24h; overdue invoices +10%/24h; single tenant >10% of requests.
All route to the email channel (v1). Use `alert_create`.

- [ ] **Step 2: Write metrics catalogue + alert runbooks**

`docs/metrics-catalogue.md`: every `sacco_*` metric, type, labels, source. `docs/alert-runbooks/<alert>.md`: trigger, likely causes, response steps, escalation — one per alert.

- [ ] **Step 3: CLAUDE.md close-out**

- Roadmap table row 5 → **Done**.
- Add an "Observability contracts (Phase 5 — do not violate)" section capturing the Global Constraints above (configure-once, scrub keyset single source of truth, no PII/secrets to telemetry, `send_to_logfire` off in tests, metric naming/labels, MRR active+trialing).
- Add a Phase 5 scope note under contract N (touches `app/core/observability/`, `app/main.py`, `app/workers/`, a few instrumentation sites, `docker-compose*.yml` env, `infra/observability/logfire/`, `docs/` — NOT `admin/`).

- [ ] **Step 4: Final gates**

Run: `ruff check app/ && mypy app/ && pytest tests/core/observability tests/test_readyz_latency.py tests/workers -v`
Expected: all clean/PASS

- [ ] **Step 5: Commit**

```bash
git add docs/alert-runbooks/ docs/metrics-catalogue.md docs/observability-runbook.md CLAUDE.md
git commit -m "feat(observability): email alerts + runbooks + CLAUDE.md close-out (Phase 5 complete)"
```

---

## Self-Review

**Spec coverage:**
- Backend = Logfire → Tasks 1, 3. ✓
- Strict egress (bind params off, bodies off, scrub) → Tasks 2, 3, 5. ✓
- `send_to_logfire` gating incl. tests-off → Task 1. ✓
- Scrub keyset single source of truth → Task 2. ✓
- Tenant/actor span context → Task 4, wired Task 5. ✓
- Auto-instrument FastAPI/SQLAlchemy/Celery/Redis/HTTPX → Tasks 3, 6. ✓
- `/readyz` per-dependency latency → Task 5. ✓
- Drop `/metrics` → not built (implicit; noted in non-goals). ✓
- Business gauges incl. MRR active+trialing, backup age → Task 8. ✓
- Custom spans/counters (outbox, maker-checker, reporting, auth) → Task 9. ✓
- Dashboards (8) via MCP + JSON → Task 10. ✓
- Alerts email-only + runbooks → Task 11. ✓
- Amounts NOT scrubbed → Task 2 (`test_amount_is_not_scrubbed`). ✓
- No portal/alembic/behaviour changes → Global Constraints; no task touches `admin/` or `alembic/`. ✓
- CLAUDE.md close-out + contracts → Task 11. ✓

**Placeholder scan:** No TBD/TODO. The one flagged uncertainty (exact `logfire` kwarg names across SDK versions) is called out in Task 3 with the invariant to preserve (no bind params leave), not left vague.

**Type consistency:** `configure_observability(service, app=None)`, `bind_actor_context(**kwargs)`, `resolve_config(service)`, `scrub_event_dict(logger, method, event_dict)`, `should_scrub(key)`, `compute_business_gauges/record_business_gauges` — names consistent across tasks and the `__init__` exports.
