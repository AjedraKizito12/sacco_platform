"""SECURITY-CRITICAL: exercise the LOGFIRE span/log scrubbing path (not just
the structlog `scrub_event_dict` processor).

FIX 1 restored Logfire's built-in secret scrubbing (the old value-returning
callback un-redacted every Logfire-default match) and layered the SACCO PII
keys on top via `ScrubbingOptions(extra_patterns=SCRUB_EXTRA_PATTERNS)`. These
tests prove Logfire redacts BOTH its own defaults (cookie/jwt/authorization)
AND our extra patterns (account_number/email) when configured with our options.

FIX 2 strips the query string off HTTP server-span URL attributes (which live
in Logfire's never-scrubbed SAFE_KEYS) via a FastAPI `server_request_hook`.
"""
from __future__ import annotations

import logfire
from fastapi import FastAPI
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from starlette.testclient import TestClient

from app.core.observability.instrument import (
    _drop_request_arguments,
    _strip_query_server_request_hook,
)
from app.core.observability.scrubbing import SCRUB_EXTRA_PATTERNS


def test_logfire_redacts_defaults_and_extra_patterns() -> None:
    exporter = InMemorySpanExporter()
    logfire.configure(
        send_to_logfire=False,
        console=False,
        scrubbing=logfire.ScrubbingOptions(extra_patterns=SCRUB_EXTRA_PATTERNS),
        additional_span_processors=[SimpleSpanProcessor(exporter)],
    )

    with logfire.span(
        "sensitive",
        # Logfire built-in defaults — must stay redacted (the old callback
        # un-redacted these):
        cookie="sessionid=deadbeef",
        jwt="eyJhbGciOi.secret.sig",
        authorization="Bearer sk-live-123",
        # SACCO extra_patterns — must be redacted by our options:
        account_number="0123456789",
        email="member@example.com",
    ):
        pass

    spans = exporter.get_finished_spans()
    assert spans, "expected at least one exported span"
    blob = "".join(str(sp.attributes or {}) for sp in spans)

    # None of the sensitive VALUES appear in clear.
    for secret in (
        "deadbeef",
        "eyJhbGciOi.secret.sig",
        "sk-live-123",
        "0123456789",
        "member@example.com",
    ):
        assert secret not in blob, f"{secret!r} leaked unscrubbed into span attrs"

    # And Logfire's redaction marker is present for each scrubbed key.
    assert "[Scrubbed due to" in blob


def test_server_span_url_has_no_query_string() -> None:
    exporter = InMemorySpanExporter()
    logfire.configure(
        send_to_logfire=False,
        console=False,
        additional_span_processors=[SimpleSpanProcessor(exporter)],
    )

    app = FastAPI()

    @app.get("/search")
    def search(q: str = "") -> dict[str, bool]:
        return {"ok": True}

    logfire.instrument_fastapi(
        app,
        server_request_hook=_strip_query_server_request_hook,
        request_attributes_mapper=_drop_request_arguments,
    )
    client = TestClient(app)
    client.get("/search?q=NATIONAL-ID-9999")

    server_spans = [
        sp for sp in exporter.get_finished_spans() if sp.kind.name == "SERVER"
    ]
    assert server_spans, "expected a SERVER-kind span"
    for sp in server_spans:
        attrs = sp.attributes or {}
        # URL attributes carry the path only, never the query string.
        for key in ("http.url", "http.target", "url.full", "url.query"):
            assert "NATIONAL-ID-9999" not in str(
                attrs.get(key, "")
            ), f"query PII leaked into {key}"
        # And the resolved-argument capture (fastapi.arguments.*) does not
        # echo the operator-typed value either.
        assert "NATIONAL-ID-9999" not in str(attrs), "query PII leaked into span"
