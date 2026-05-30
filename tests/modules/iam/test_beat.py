

def test_beat_module_imports_without_error():
    """Smoke test — verify the beat module loads and exposes the expected task names."""
    import app.modules.iam.beat as beat_module

    assert hasattr(beat_module, "advance_key_lifecycle")
    assert hasattr(beat_module, "rotate_signing_keys_if_due")


def test_advance_key_lifecycle_is_registered_celery_task():
    from app.workers.celery_app import celery_app

    assert "app.modules.iam.beat.advance_key_lifecycle" in celery_app.tasks


def test_rotate_signing_keys_if_due_is_registered_celery_task():
    from app.workers.celery_app import celery_app

    assert "app.modules.iam.beat.rotate_signing_keys_if_due" in celery_app.tasks


def test_cleanup_sessions_is_registered_celery_task():
    from app.workers.celery_app import celery_app

    assert "app.modules.iam.beat.cleanup_sessions" in celery_app.tasks
