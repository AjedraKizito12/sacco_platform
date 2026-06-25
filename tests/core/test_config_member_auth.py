from __future__ import annotations

import base64

import pytest

from app.core.config import Settings


def _base_env() -> dict[str, str]:
    return {
        "app_secret_key": "x" * 32,
        "database_url": "postgresql+asyncpg://u:p@localhost/db",
        "jwt_kek": base64.b64encode(b"\x01" * 32).decode(),
    }


def test_member_auth_mode_defaults_to_jwt() -> None:
    s = Settings(**_base_env())
    assert s.member_auth_mode == "jwt"
    assert s.jwt_refresh_ttl_member_seconds == 28800


def test_member_jwt_mode_requires_jwt_kek() -> None:
    env = _base_env()
    env["jwt_kek"] = ""
    env["platform_auth_mode"] = "stub"
    env["tenant_auth_mode"] = "stub"
    env["member_auth_mode"] = "jwt"
    with pytest.raises(ValueError, match="JWT_KEK"):
        Settings(**env)


def test_member_stub_mode_allowed_without_kek() -> None:
    env = _base_env()
    env["jwt_kek"] = ""
    env["platform_auth_mode"] = "stub"
    env["tenant_auth_mode"] = "stub"
    env["member_auth_mode"] = "stub"
    s = Settings(**env)
    assert s.member_auth_mode == "stub"
