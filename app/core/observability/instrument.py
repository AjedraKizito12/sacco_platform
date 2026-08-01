from __future__ import annotations

import os
from typing import Any, Literal, cast

import logfire

from app.core.observability.config import resolve_config
from app.core.observability.scrubbing import scrubbing_callback

_configured = False
_libraries_instrumented = False
_fastapi_instrumented = False


def _in_pytest() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ


def configure_observability(service: str, app: object | None = None) -> None:
    """Configure Logfire once (idempotent) and auto-instrument libraries.

    Egress posture is strict/metadata-only: telemetry is NEVER shipped during
    a pytest run, even if `resolve_config` would otherwise enable it (e.g. a
    test setting APP_ENV=staging + LOGFIRE_TOKEN). This guard is deliberately
    layered on top of `resolve_config`, which stays pure/environment-driven.
    """
    global _configured
    cfg = resolve_config(service=service)
    effective_send = cfg.send_to_logfire and not _in_pytest()

    if not _configured:
        console: logfire.ConsoleOptions | Literal[False] | None
        if effective_send:
            console = False
        elif _in_pytest():
            # Keep pytest output clean even though we're not shipping.
            console = False
        else:
            # Local dev, not shipping: default console ON so devs see traces.
            console = None

        logfire.configure(
            service_name=f"sacco-{service}",
            environment=cfg.environment,
            token=cfg.token,
            send_to_logfire=effective_send,
            scrubbing=logfire.ScrubbingOptions(callback=scrubbing_callback),
            console=console,
        )
        _configured = True

    instrument_all(app=app)


def instrument_all(app: object | None = None) -> None:
    """Auto-instrument FastAPI/SQLAlchemy/Celery/Redis/HTTPX with strict defaults.

    All library instrumentors use SDK defaults, which already keep bind
    parameters, headers, and request/response bodies out of spans. Library
    instrumentors are idempotent-guarded here to avoid duplicate-instrumentation
    warnings when `configure_observability` is called more than once (e.g. in
    tests). FastAPI instrumentation is guarded separately since the worker
    path calls this with `app=None` while the API path passes a real app.
    """
    global _libraries_instrumented, _fastapi_instrumented

    if not _libraries_instrumented:
        # SQL: statement shape only — OTel SQLAlchemy does not capture bind
        # parameters by default; never enable parameter capture here.
        logfire.instrument_sqlalchemy(enable_commenter=False)
        logfire.instrument_redis()
        logfire.instrument_httpx()
        logfire.instrument_celery()
        _libraries_instrumented = True

    if app is not None and not _fastapi_instrumented:
        # capture_headers/record_send_receive default False: no header or
        # request/response body capture. `app` is typed loosely (object) here
        # to avoid a hard FastAPI import dependency in this module; the
        # caller (app/main.py, Task 5) always passes a real FastAPI instance.
        logfire.instrument_fastapi(cast(Any, app))
        _fastapi_instrumented = True
