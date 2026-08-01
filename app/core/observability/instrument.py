from __future__ import annotations

import os
from typing import Any, Literal, cast

import logfire

from app.core.observability.config import resolve_config
from app.core.observability.scrubbing import SCRUB_EXTRA_PATTERNS

_configured = False
_libraries_instrumented = False
_fastapi_instrumented = False

# URL-ish server-span attributes that may carry a raw request URL including the
# query string. Logfire's SAFE_KEYS list (logfire/_internal/scrubbing.py) treats
# these as never-scrubbed, so operator-typed member PII in a query string
# (e.g. GET /search?q=<national-id>) would egress unscrubbed. The
# `_strip_query_server_request_hook` below drops the query portion at span
# start, before any exporter sees it.
_URL_QUERY_ATTRS = ("http.url", "http.target", "url.full")


def _in_pytest() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ


def _strip_query_server_request_hook(span: Any, scope: Any) -> None:
    """OTel FastAPI `server_request_hook`: strip the query string off the
    HTTP server span's URL attributes.

    # SECURITY: url.full / http.url / http.target / url.query are in Logfire's
    # SAFE_KEYS and are NEVER scrubbed. Free-text operator endpoints
    # (GET /search?q=…, list filters) put member PII in the query string, which
    # would otherwise egress in clear. The hook receives the LIVE span at
    # request start (attributes already populated by the ASGI instrumentor) and
    # overwrites them with the path-only form via set_attribute.
    """
    if span is None or not getattr(span, "is_recording", lambda: False)():
        return
    attrs = span.attributes or {}
    for key in _URL_QUERY_ATTRS:
        value = attrs.get(key)
        if isinstance(value, str) and "?" in value:
            span.set_attribute(key, value.split("?", 1)[0])
    # url.query, if present, is the query string on its own — blank it.
    if isinstance(attrs.get("url.query"), str) and attrs.get("url.query"):
        span.set_attribute("url.query", "")


def _drop_request_arguments(request: Any, attributes: Any) -> None:
    """OTel FastAPI `request_attributes_mapper`: drop the captured endpoint
    argument values from the server span.

    # SECURITY: logfire.instrument_fastapi records the RESOLVED endpoint
    # arguments under `fastapi.arguments.values`/`.errors`. For free-text
    # operator endpoints (GET /search?q=…, list filters keyed q/name/etc.)
    # those values are operator-typed member PII that Logfire's key-name
    # scrubber cannot catch (the param key `q` matches nothing). Returning None
    # records no argument attributes — consistent with the strict/metadata-only
    # egress posture. Validation-error shapes are dropped too because they echo
    # the raw input value.
    """
    return None


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
            scrubbing=logfire.ScrubbingOptions(extra_patterns=SCRUB_EXTRA_PATTERNS),
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
        logfire.instrument_fastapi(
            cast(Any, app),
            server_request_hook=_strip_query_server_request_hook,
            request_attributes_mapper=_drop_request_arguments,
        )
        _fastapi_instrumented = True
