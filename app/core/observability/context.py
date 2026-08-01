from __future__ import annotations

import structlog
from opentelemetry import trace


def bind_actor_context(**kwargs: str) -> None:
    """Bind actor/tenant identifiers to both the structlog contextvars and the
    current span. Ids/labels only -- never PII. This is the single wrapper the
    auth deps call in place of a bare structlog.contextvars.bind_contextvars.
    """
    structlog.contextvars.bind_contextvars(**kwargs)
    span = trace.get_current_span()
    if span is not None and span.is_recording():
        for key, value in kwargs.items():
            span.set_attribute(key, value)
