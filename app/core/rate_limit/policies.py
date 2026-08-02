from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Literal

Audience = Literal["anonymous", "tenant", "member", "platform"]


@dataclass(frozen=True)
class Policy:
    name: str
    limit: int
    window_seconds: int


# Ordered, most-specific first. (audience_scope, glob, Policy).
# audience_scope: "anonymous" | "authenticated" (tenant+member+platform) | "platform".
_RULES: list[tuple[str, str, Policy]] = [
    ("anonymous", "/auth/token", Policy("auth_login", 10, 60)),
    ("anonymous", "/platform/auth/token", Policy("auth_login", 10, 60)),
    ("anonymous", "/member/auth/token", Policy("auth_login", 10, 60)),
    ("anonymous", "*password-reset*", Policy("auth_password_reset", 3, 900)),
    ("anonymous", "*", Policy("anonymous_default", 60, 60)),
    ("platform", "/platform/*", Policy("platform_admin", 600, 60)),
    ("authenticated", "/reporting/*", Policy("reporting", 60, 60)),
    ("authenticated", "*statement*", Policy("export", 10, 60)),
    ("authenticated", "*/export*", Policy("export", 10, 60)),
    ("authenticated", "*", Policy("authenticated_default", 300, 60)),
]


def _scope_matches(scope: str, audience: Audience) -> bool:
    if scope == "anonymous":
        return audience == "anonymous"
    if scope == "platform":
        return audience == "platform"
    # "authenticated"
    return audience in ("tenant", "member", "platform")


def match_policy(path: str, audience: Audience) -> Policy:
    for scope, glob, policy in _RULES:
        if _scope_matches(scope, audience) and fnmatch.fnmatch(path, glob):
            return policy
    # Unreachable in practice (each audience has a "*" catch-all) but keep total.
    return Policy("authenticated_default", 300, 60)
