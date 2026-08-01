from app.core.observability.config import resolve_config


def test_no_token_non_prod_disables_egress(monkeypatch):
    monkeypatch.delenv("LOGFIRE_TOKEN", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    cfg = resolve_config(service="api")
    assert cfg.send_to_logfire is False
    assert cfg.service == "api"
    assert cfg.environment == "development"


def test_token_enables_egress(monkeypatch):
    monkeypatch.setenv("LOGFIRE_TOKEN", "pylf_test")
    monkeypatch.setenv("APP_ENV", "staging")
    cfg = resolve_config(service="worker")
    assert cfg.send_to_logfire is True


def test_tests_env_always_disables_egress(monkeypatch):
    # Even with a token, APP_ENV=test must never ship telemetry.
    monkeypatch.setenv("LOGFIRE_TOKEN", "pylf_test")
    monkeypatch.setenv("APP_ENV", "test")
    cfg = resolve_config(service="api")
    assert cfg.send_to_logfire is False
