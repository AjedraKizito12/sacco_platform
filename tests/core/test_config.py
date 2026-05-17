import os
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
