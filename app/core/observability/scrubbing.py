from __future__ import annotations

from typing import Any

SCRUB_KEYS: frozenset[str] = frozenset({
    "password", "token", "secret", "jwt_kek", "hashed_password",
    "national_id_number", "email", "phone", "first_name", "last_name", "dob",
    # Email-bearing display label (e.g. "user@example.com (impersonating)");
    # telemetry-sensitive even though it's needed in the structlog/audit trail.
    "actor_label",
})

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


def scrubbing_callback(match: Any) -> Any:
    """Logfire ScrubbingOptions callback. Return None to redact.

    Logfire calls this for every value whose path matches its own patterns;
    we additionally redact anything matching our keyset by path key name.
    """
    path_keys = [str(p) for p in getattr(match, "path", [])]
    if any(should_scrub(k) for k in path_keys):
        return None
    return match.value
