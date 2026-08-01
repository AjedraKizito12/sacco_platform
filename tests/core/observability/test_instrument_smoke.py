import logfire

from app.core.observability import configure_observability


def test_configure_is_idempotent_and_offline_under_tests(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LOGFIRE_TOKEN", "pylf_test")  # must still be offline
    # Should not raise, and calling twice is safe.
    configure_observability(service="api")
    configure_observability(service="api")
    # A span works without shipping anywhere.
    with logfire.span("smoke"):
        pass
