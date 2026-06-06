"""Exceptions raised by ImpersonationService."""
from __future__ import annotations


class ImpersonationGone(Exception):
    """The impersonation has ended, been revoked, or expired.

    Mapped to HTTP 410 by the API layer.
    """


class ImpersonationNotActive(Exception):
    """The impersonation row exists but is not yet usable (no approval has
    executed yet, or the row is in a transient state).

    Mapped to HTTP 409 by the API layer.
    """
