import logfire
import structlog
from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from app.core.observability import configure_observability
from app.core.observability.context import bind_actor_context


def test_bind_actor_context_sets_structlog_and_span(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    configure_observability(service="api")
    structlog.contextvars.clear_contextvars()

    # `configure_observability` is idempotent (process-global TracerProvider),
    # so it may already have been configured by an earlier test without our
    # exporter wired in. Reading attributes straight off the live span handle
    # is not reliably supported across OTel SDK versions either. Instead,
    # attach an in-memory exporter directly to the current (real OTel) tracer
    # provider and assert on the exported, finished span -- a real behavioral
    # check that the attributes actually land on the span.
    exporter = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))  # type: ignore[attr-defined]

    with logfire.span("req"):
        bind_actor_context(
            actor_type="tenant_user",
            actor_id="00000000-0000-0000-0000-000000000001",
            tenant_schema="tenant_acme",
        )

    finished = exporter.get_finished_spans()
    assert len(finished) == 1
    attrs = finished[0].attributes or {}
    assert attrs.get("actor_type") == "tenant_user"
    assert attrs.get("actor_id") == "00000000-0000-0000-0000-000000000001"
    assert attrs.get("tenant_schema") == "tenant_acme"

    # structlog contextvars also carry it (unchanged existing behaviour).
    ctx = structlog.contextvars.get_contextvars()
    assert ctx["actor_type"] == "tenant_user"
    assert ctx["tenant_schema"] == "tenant_acme"


def test_bind_actor_context_noop_when_no_recording_span():
    structlog.contextvars.clear_contextvars()
    # No active span -- should not raise, and should still bind contextvars.
    bind_actor_context(actor_type="platform_user")
    ctx = structlog.contextvars.get_contextvars()
    assert ctx["actor_type"] == "platform_user"
