import structlog
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from app.core.observability.context import bind_actor_context
from app.core.observability.scrubbing import scrub_event_dict


def test_bind_actor_context_sets_structlog_and_span():
    # Own a LOCAL TracerProvider so the in-memory exporter never touches the
    # process-global provider -- no leaked span processor, no cross-test
    # pollution. `bind_actor_context` reads `trace.get_current_span()` from the
    # context, which `start_as_current_span` sets regardless of the global
    # provider, so the behavioural assertion on exported spans still holds.
    exporter = InMemorySpanExporter()
    local_provider = TracerProvider()
    local_provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = local_provider.get_tracer("test-context")

    structlog.contextvars.clear_contextvars()
    with tracer.start_as_current_span("req"):
        bind_actor_context(
            actor_type="tenant_user",
            actor_id="00000000-0000-0000-0000-000000000001",
            tenant_schema="tenant_acme",
        )
    local_provider.shutdown()

    finished = exporter.get_finished_spans()
    assert len(finished) == 1
    attrs = finished[0].attributes or {}
    assert attrs["actor_type"] == "tenant_user"
    assert attrs["actor_id"] == "00000000-0000-0000-0000-000000000001"
    assert attrs["tenant_schema"] == "tenant_acme"

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


def test_bind_actor_context_never_sets_actor_label_as_span_attribute():
    # PII enforcement (SECURITY-CRITICAL): actor_label carries an email
    # address and must never reach a span, even though it's needed in the
    # structlog contextvars for AuditableMixin's audit trail.
    exporter = InMemorySpanExporter()
    local_provider = TracerProvider()
    local_provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = local_provider.get_tracer("test-context-pii")

    structlog.contextvars.clear_contextvars()
    with tracer.start_as_current_span("req"):
        bind_actor_context(
            actor_type="tenant_user",
            actor_id="00000000-0000-0000-0000-000000000002",
            actor_label="a@b.com",
        )
    local_provider.shutdown()

    finished = exporter.get_finished_spans()
    assert len(finished) == 1
    attrs = finished[0].attributes or {}
    assert attrs["actor_type"] == "tenant_user"
    assert attrs["actor_id"] == "00000000-0000-0000-0000-000000000002"
    assert "actor_label" not in attrs

    # structlog contextvars still carry actor_label -- audit trail is intact.
    ctx = structlog.contextvars.get_contextvars()
    assert ctx["actor_label"] == "a@b.com"


def test_scrub_event_dict_redacts_actor_label():
    out = scrub_event_dict(
        None,
        "info",
        {"event": "x", "actor_label": "a@b.com (impersonating)"},
    )
    assert out["actor_label"] == "[scrubbed]"
