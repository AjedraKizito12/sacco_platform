import base64

import pytest

# conftest.py sets DATABASE_URL and APP_SECRET_KEY before this import.
from app.core.config import Settings, get_settings


def test_settings_load_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/mydb")
    monkeypatch.setenv("APP_SECRET_KEY", "supersecret")
    s = Settings()
    assert s.database_url == "postgresql+asyncpg://u:p@db:5432/mydb"
    assert s.app_secret_key == "supersecret"


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db/d")
    monkeypatch.setenv("APP_SECRET_KEY", "s")
    s = Settings()
    assert s.app_env == "development"
    assert s.redis_url == "redis://localhost:6379/0"
    assert s.db_pool_size == 10
    assert s.db_max_overflow == 20
    assert s.slow_query_ms == 200
    assert s.structlog_json is False
    assert s.request_id_header == "X-Request-ID"
    assert s.tenant_header == "X-Tenant-Slug"


def test_settings_allowed_origins_parsed_as_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db/d")
    monkeypatch.setenv("APP_SECRET_KEY", "s")
    monkeypatch.setenv("ALLOWED_ORIGINS", '["http://localhost:3000","http://localhost:8080"]')
    s = Settings()
    assert s.allowed_origins == ["http://localhost:3000", "http://localhost:8080"]


def test_get_settings_is_cached() -> None:
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_jwt_kek_validator_rejects_wrong_length():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="32 bytes"):
        Settings(
            database_url="postgresql+asyncpg://x:x@localhost/x",
            app_secret_key="x",
            platform_auth_mode="stub",
            tenant_auth_mode="stub",
            jwt_kek=base64.b64encode(b"tooshort").decode(),
        )


def test_jwt_kek_validator_rejects_bad_base64():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="base64"):
        Settings(
            database_url="postgresql+asyncpg://x:x@localhost/x",
            app_secret_key="x",
            platform_auth_mode="stub",
            tenant_auth_mode="stub",
            jwt_kek="!!!not-valid-base64!!!",
        )


def test_jwt_kek_validator_accepts_empty_string():
    """Field-level validator accepts empty string — model validator permits it
    when auth modes are stub. Production enforcement is handled by the model
    validator (test_model_validator_rejects_empty_kek_with_jwt_* tests above)."""
    s = Settings(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        app_secret_key="x",
        platform_auth_mode="stub",
        tenant_auth_mode="stub",
        jwt_kek="",
    )
    assert s.jwt_kek == ""


def test_jwt_kek_validator_accepts_valid_32_byte_key():
    kek = base64.b64encode(b"\xab" * 32).decode()
    s = Settings(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        app_secret_key="x",
        jwt_kek=kek,
    )
    assert s.jwt_kek == kek


_VALID_KEK = base64.b64encode(b"\x01" * 32).decode()
_STUB_MODES = {"platform_auth_mode": "stub", "tenant_auth_mode": "stub"}


def test_auth_password_min_length_defaults_to_12():
    s = Settings(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        app_secret_key="x",
        **_STUB_MODES,
    )
    assert s.auth_password_min_length == 12


def test_auth_password_min_length_is_configurable():
    s = Settings(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        app_secret_key="x",
        **_STUB_MODES,
        auth_password_min_length=16,
    )
    assert s.auth_password_min_length == 16


def test_lockout_defaults():
    s = Settings(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        app_secret_key="x",
        **_STUB_MODES,
    )
    assert s.auth_lockout_threshold == 5
    assert s.auth_lockout_window_minutes == 15
    assert s.auth_lockout_duration_minutes == 30


def test_lockout_settings_are_configurable():
    s = Settings(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        app_secret_key="x",
        **_STUB_MODES,
        auth_lockout_threshold=3,
        auth_lockout_window_minutes=10,
        auth_lockout_duration_minutes=60,
    )
    assert s.auth_lockout_threshold == 3
    assert s.auth_lockout_window_minutes == 10
    assert s.auth_lockout_duration_minutes == 60


def test_tenant_auth_mode_defaults_to_jwt():
    """After Plan 12 the model-field default for TENANT_AUTH_MODE is 'jwt'.

    We check the class-level default rather than instantiating Settings, because
    conftest.py pre-seeds TENANT_AUTH_MODE=stub in os.environ (keeping the test
    suite in stub mode) — pydantic-settings would resolve the env var first.
    """
    assert Settings.model_fields["tenant_auth_mode"].default == "jwt"


def test_platform_auth_mode_defaults_to_jwt():
    """After Plan 12 the model-field default for PLATFORM_AUTH_MODE is 'jwt'.

    See test_tenant_auth_mode_defaults_to_jwt for why we check the class default.
    """
    assert Settings.model_fields["platform_auth_mode"].default == "jwt"


def test_tenant_auth_mode_is_configurable():
    s = Settings(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        app_secret_key="x",
        platform_auth_mode="stub",
        tenant_auth_mode="stub",
    )
    assert s.tenant_auth_mode == "stub"


def test_model_validator_rejects_empty_kek_with_jwt_platform_mode():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="JWT_KEK"):
        Settings(
            database_url="postgresql://x",
            app_secret_key="y",
            platform_auth_mode="jwt",
            tenant_auth_mode="stub",
            jwt_kek="",
        )


def test_model_validator_rejects_empty_kek_with_jwt_tenant_mode():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="JWT_KEK"):
        Settings(
            database_url="postgresql://x",
            app_secret_key="y",
            platform_auth_mode="stub",
            tenant_auth_mode="jwt",
            jwt_kek="",
        )


def test_model_validator_permits_empty_kek_in_full_stub_mode():
    """Both modes stub → jwt_kek not required."""
    s = Settings(
        database_url="postgresql://x",
        app_secret_key="y",
        **_STUB_MODES,
        jwt_kek="",
    )
    assert s.jwt_kek == ""


def test_model_validator_accepts_valid_kek_with_jwt_modes():
    s = Settings(
        database_url="postgresql://x",
        app_secret_key="y",
        platform_auth_mode="jwt",
        tenant_auth_mode="jwt",
        jwt_kek=_VALID_KEK,
    )
    assert s.jwt_kek == _VALID_KEK
