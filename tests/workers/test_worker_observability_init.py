from unittest.mock import patch

from app.workers import celery_app as celery_mod


def test_worker_init_configures_observability(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    with patch("app.core.observability.configure_observability") as cfg:
        celery_mod._init_observability()  # signal handler body, extracted for testability
        cfg.assert_called_once()
        assert cfg.call_args.kwargs["service"] in {"worker", "beat"}
