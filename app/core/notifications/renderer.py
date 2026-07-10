"""Sandboxed Jinja2 rendering for notification templates."""
from __future__ import annotations

from typing import Any

from jinja2.sandbox import SandboxedEnvironment

_HTML_ENV = SandboxedEnvironment(autoescape=True)
_TEXT_ENV = SandboxedEnvironment(autoescape=False)  # noqa: S701 — plain text/sms output


def render(template_str: str, context: dict[str, Any], *, html: bool) -> str:
    env = _HTML_ENV if html else _TEXT_ENV
    return env.from_string(template_str).render(**context)
