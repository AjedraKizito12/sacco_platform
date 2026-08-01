from __future__ import annotations

import os
from dataclasses import dataclass

from app.core.config import get_settings


@dataclass(frozen=True)
class ObservabilityConfig:
    token: str | None
    environment: str
    service: str
    send_to_logfire: bool


def _is_test_env(environment: str) -> bool:
    return environment == "test"


def resolve_config(service: str) -> ObservabilityConfig:
    settings = get_settings()
    environment = settings.app_env
    token = os.environ.get("LOGFIRE_TOKEN") or None
    send = False if _is_test_env(environment) else token is not None
    return ObservabilityConfig(
        token=token, environment=environment, service=service, send_to_logfire=send
    )
