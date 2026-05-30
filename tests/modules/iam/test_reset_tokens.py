"""Unit tests for HMAC-SHA256 password reset token helpers.

No DB, no Redis, no async — these are pure synchronous functions.
"""
from __future__ import annotations

import time

import pytest

from app.modules.iam.reset_tokens import make_reset_token, verify_reset_token


def test_make_and_verify_round_trip() -> None:
    token, jti = make_reset_token("user-id-abc", "test-secret")
    payload = verify_reset_token(token, "test-secret")
    assert payload["sub"] == "user-id-abc"
    assert payload["jti"] == jti
    assert payload["type"] == "password_reset"


def test_jti_is_unique_per_call() -> None:
    _, jti1 = make_reset_token("user-id", "secret")
    _, jti2 = make_reset_token("user-id", "secret")
    assert jti1 != jti2


def test_wrong_secret_raises_value_error() -> None:
    token, _ = make_reset_token("user-id-abc", "correct-secret")
    with pytest.raises(ValueError, match="invalid token signature"):
        verify_reset_token(token, "wrong-secret")


def test_expired_token_raises_value_error() -> None:
    # ttl=-1 puts exp in the past.
    token, _ = make_reset_token("user-id-abc", "secret", ttl=-1)
    with pytest.raises(ValueError, match="token has expired"):
        verify_reset_token(token, "secret")


def test_tampered_signature_raises_value_error() -> None:
    token, _ = make_reset_token("user-id-abc", "secret")
    # Replace last 8 chars of signature with garbage.
    tampered = token[:-8] + "xxxxxxxx"
    with pytest.raises(ValueError, match="invalid token signature"):
        verify_reset_token(tampered, "secret")


def test_malformed_token_missing_dot_raises_value_error() -> None:
    with pytest.raises(ValueError, match="malformed token"):
        verify_reset_token("nodothere", "secret")


def test_wrong_token_type_raises_value_error() -> None:
    """A JWT or other token that happens to be valid HMAC must still be rejected."""
    import base64
    import hashlib
    import hmac
    import json

    payload = {"sub": "x", "jti": "y", "exp": int(time.time()) + 900, "type": "access"}
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).rstrip(b"=").decode()
    sig = hmac.new(b"secret", payload_b64.encode(), hashlib.sha256).hexdigest()
    token = f"{payload_b64}.{sig}"
    with pytest.raises(ValueError, match="wrong token type"):
        verify_reset_token(token, "secret")


def test_make_reset_token_returns_string() -> None:
    token, jti = make_reset_token("uid", "s")
    assert isinstance(token, str)
    assert isinstance(jti, str)
    assert "." in token  # payload.signature
