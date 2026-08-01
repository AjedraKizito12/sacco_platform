from __future__ import annotations

import structlog
from opentelemetry import trace

# Only these keys are safe to set as span attributes -- span data can be
# forwarded to Logfire. `actor_label` (which carries an email address) is
# deliberately excluded: it is bound to structlog contextvars only, so
# AuditableMixin still sees it, but it never becomes telemetry.
_SPAN_SAFE_KEYS = frozenset({
    "actor_type", "actor_id", "tenant_schema", "impersonation_id", "request_id",
})


def bind_actor_context(**kwargs: str) -> None:
    """Bind actor/tenant identifiers to both the structlog contextvars and the
    current span. This is the single wrapper the auth deps call in place of a
    bare structlog.contextvars.bind_contextvars.

    ALL kwargs are bound to structlog contextvars (AuditableMixin reads them
    directly for the audit trail). Only keys in `_SPAN_SAFE_KEYS` are set as
    span attributes -- PII-bearing values such as `actor_label` (email) must
    never reach a span.
    """
    structlog.contextvars.bind_contextvars(**kwargs)
    span = trace.get_current_span()
    if span is not None and span.is_recording():
        for key, value in kwargs.items():
            if key in _SPAN_SAFE_KEYS:
                span.set_attribute(key, value)
