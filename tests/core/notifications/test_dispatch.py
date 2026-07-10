"""Notifications: renderer, providers, dispatcher, beat."""
from __future__ import annotations

import pytest

from app.core.notifications.renderer import render

SCHEMA = "tenant_test"


def test_render_text_and_html_escaping() -> None:
    assert render("Hi {{ name }}", {"name": "Ada"}, html=False) == "Hi Ada"
    assert render("<b>{{ v }}</b>", {"v": "<x>"}, html=True) == "<b>&lt;x&gt;</b>"
    assert render("{{ v }}", {"v": "<x>"}, html=False) == "<x>"


def test_render_is_sandboxed() -> None:
    with pytest.raises(Exception):  # noqa: B017 — SecurityError from the sandbox
        render("{{ ''.__class__.__mro__ }}", {}, html=False)


async def test_null_and_log_providers() -> None:
    from app.core.notifications.providers.log import LogEmailProvider, LogSMSProvider
    from app.core.notifications.providers.null import NullEmailProvider, NullSMSProvider

    assert NullEmailProvider.name == "null"
    assert LogEmailProvider.name == "log"
    assert await NullEmailProvider().send(to="a@b.c", subject="s", text="t", html=None) is None
    assert await NullSMSProvider().send(to="+256", body="b") is None
    assert await LogEmailProvider().send(to="a@b.c", subject="s", text="t", html=None)
    assert await LogSMSProvider().send(to="+256", body="b")


def test_provider_factory_defaults_to_null() -> None:
    from app.core.notifications import providers
    from app.core.notifications.providers.null import NullEmailProvider

    assert isinstance(providers.get_email_provider(), NullEmailProvider)
