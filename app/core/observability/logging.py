from __future__ import annotations

from app.core.observability.scrubbing import scrub_event_dict

# The existing structlog config lives in app.main._configure_logging().
# Task 3 inserts `scrub_event_dict` into that processor chain (before the
# renderer) and appends the Logfire structlog processor so log records with
# scrubbed keys become Logfire log records. This module re-exports the
# processor so main.py imports from one place.

__all__ = ["scrub_event_dict"]
