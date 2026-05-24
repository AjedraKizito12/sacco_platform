"""HMAC-SHA256 signed password reset tokens.

Token format (URL-safe string):
    <base64url-payload>.<hex-hmac-signature>

Payload JSON fields:
    sub   : str  — user ID (UUID string)
    jti   : str  — unique token ID; caller stores in Redis for one-use enforcement
    exp   : int  — Unix timestamp of expiry
    type  : str  — always "password_reset" (rejects tokens issued for other purposes)

The signing key is passed explicitly so both platform and tenant callers can
use the same secret (settings.app_secret_key) or different ones if needed.

Redis tracking is NOT handled here — this module only creates and verifies
tokens. The caller is responsible for:
  1. After make_reset_token: SET iam:pwreset:{jti} "1" EX <ttl> in Redis.
  2. Before consuming: EXISTS iam:pwreset:{jti} → reject if 0.
  3. After confirming: DEL iam:pwreset:{jti} in Redis.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid

_RESET_TTL_SECONDS = 900  # 15 minutes


def make_reset_token(
    user_id: str,
    secret: str,
    ttl: int = _RESET_TTL_SECONDS,
) -> tuple[str, str]:
    """Create a signed password reset token.

    Args:
        user_id: UUID string of the user requesting the reset.
        secret:  HMAC signing key (use settings.app_secret_key).
        ttl:     Lifetime in seconds. Defaults to 900 (15 minutes).

    Returns:
        (token, jti) — ``token`` is the opaque string to deliver to the user
        (via email or log); ``jti`` is the unique token ID the caller stores
        in Redis with ``EX ttl``.
    """
    jti = str(uuid.uuid4())
    payload = {
        "sub": user_id,
        "jti": jti,
        "exp": int(time.time()) + ttl,
        "type": "password_reset",
    }
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .rstrip(b"=")
        .decode()
    )
    sig = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}", jti


def verify_reset_token(token: str, secret: str) -> dict[str, str | int]:
    """Verify a signed reset token and return its payload.

    Args:
        token:  The opaque token string returned by ``make_reset_token``.
        secret: HMAC signing key — must match the one used to create the token.

    Returns:
        Payload dict with keys: ``sub``, ``jti``, ``exp``, ``type``.

    Raises:
        ValueError: token is malformed, signature is invalid, token has
                    expired, or token type is not "password_reset".
    """
    parts = token.split(".", 1)
    if len(parts) != 2:
        raise ValueError("malformed token: missing signature separator")
    payload_b64, sig = parts

    expected_sig = hmac.new(
        secret.encode(), payload_b64.encode(), hashlib.sha256
    ).hexdigest()
    # Constant-time comparison prevents timing attacks.
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("invalid token signature")

    # Restore base64 padding before decoding.
    rem = len(payload_b64) % 4
    if rem:
        payload_b64 += "=" * (4 - rem)

    try:
        payload: dict[str, str | int] = json.loads(
            base64.urlsafe_b64decode(payload_b64)
        )
    except Exception as exc:
        raise ValueError("malformed token payload") from exc

    if payload.get("type") != "password_reset":
        raise ValueError("wrong token type")

    if int(payload["exp"]) < int(time.time()):
        raise ValueError("token has expired")

    return payload
