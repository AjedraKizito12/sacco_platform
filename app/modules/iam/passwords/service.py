"""argon2id password hashing using passlib.

A single module-level ``CryptContext`` is configured at OWASP-recommended
server-side parameters and reused across all calls. The context lists
``bcrypt`` as a deprecated fallback scheme so that any legacy bcrypt hashes
already in the database can still be verified — ``needs_rehash`` will return
``True`` for those, triggering a transparent upgrade on next successful login.

OWASP argon2id recommendations (server-side, 2023):
    memory_cost  = 64 MB (65536 KiB)
    time_cost    = 3 iterations
    parallelism  = 4 threads

Do not change these defaults without re-reviewing the OWASP guidance and
updating the ``@validator`` in Settings if the minimum-length rule changes.
"""
from __future__ import annotations

from passlib.context import CryptContext

from app.core.config import get_settings

_pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    deprecated=["bcrypt"],
    # argon2id parameters — OWASP server-side recommendations.
    argon2__memory_cost=65536,  # 64 MB in KiB
    argon2__time_cost=3,
    argon2__parallelism=4,
)


def hash_password(plain: str) -> str:
    """Hash *plain* using argon2id and return the passlib-formatted hash string.

    Validates minimum password length before hashing. Raises ``ValueError``
    if the password is shorter than ``settings.auth_password_min_length``.

    The returned string is safe to store directly in the ``hashed_password``
    column — it includes the algorithm, version, parameters, salt, and hash
    in a self-describing format (``$argon2id$v=19$...``).
    """
    min_length = get_settings().auth_password_min_length
    if len(plain) < min_length:
        raise ValueError(
            f"Password must be at least {min_length} characters"
        )
    return str(_pwd_context.hash(plain))


def verify_password(plain: str, hashed: str) -> bool:
    """Return ``True`` if *plain* matches *hashed*, ``False`` otherwise.

    Uses passlib's constant-time comparison. Safe to call with hashes
    produced by any scheme registered in the context (argon2id or legacy
    bcrypt). Returns ``False`` — never raises — for any verification failure.
    """
    try:
        return bool(_pwd_context.verify(plain, hashed))
    except Exception:
        return False


def needs_rehash(hashed: str) -> bool:
    """Return ``True`` if *hashed* was produced with outdated parameters.

    Call this after a successful ``verify_password`` and, if ``True``,
    immediately hash the plaintext again with ``hash_password`` and persist
    the new hash. This provides transparent parameter upgrades without
    requiring users to change their passwords.

    Returns ``True`` for:
    - Hashes produced with an older argon2id parameter set (e.g., lower
      memory_cost before a future parameter upgrade).
    - Any hash produced by a deprecated scheme (e.g., legacy bcrypt).
    """
    return bool(_pwd_context.needs_update(hashed))
