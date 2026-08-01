from __future__ import annotations

from typing import Any

# Keys used by the structlog `scrub_event_dict` processor path. Any structlog
# event-dict key that substring-matches one of these (case-insensitively) has
# its value replaced with `_REDACTION`. This is the SACCO-specific keyset; the
# Logfire span/log path uses `SCRUB_EXTRA_PATTERNS` below (on top of Logfire's
# own built-in defaults).
SCRUB_KEYS: frozenset[str] = frozenset({
    "password", "token", "secret", "jwt_kek", "hashed_password",
    "national_id_number", "email", "phone", "first_name", "last_name", "dob",
    # Email-bearing display label (e.g. "user@example.com (impersonating)");
    # telemetry-sensitive even though it's needed in the structlog/audit trail.
    "actor_label",
    # Financial / identity keys — keep the structlog path consistent with the
    # Logfire extra-patterns keyset below.
    "member_number", "account_number", "card_number", "passport",
    "routing_number",
})

# Regex substring patterns matched by Logfire against attribute key paths, ON
# TOP OF Logfire's own built-in DEFAULT_PATTERNS (password, auth, authorization,
# credential, api_key, session, cookie, jwt, ssn, credit_card, ...). Passed as
# `ScrubbingOptions(extra_patterns=SCRUB_EXTRA_PATTERNS)` — this ADDS the SACCO
# PII/secret keys to Logfire's scrubbing; it never disables the defaults.
SCRUB_EXTRA_PATTERNS: list[str] = [
    "national_id",
    "first_name",
    "last_name",
    r"\bdob\b",
    "actor_label",
    "email",
    "phone",
    "member_number",
    "account_number",
    "card_number",
    "passport",
    "routing_number",
]

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
