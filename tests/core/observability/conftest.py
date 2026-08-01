import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Clear get_settings() lru_cache before each test to allow monkeypatch to work."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
