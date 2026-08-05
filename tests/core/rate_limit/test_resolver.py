from app.core.rate_limit.policies import Policy
from app.core.rate_limit.resolver import apply_overrides


def test_apply_overrides_changes_matched_policy():
    base = Policy("reporting", 60, 60)
    out = apply_overrides(base, {"reporting": {"limit": 120, "window_seconds": 60}})
    assert (out.limit, out.window_seconds) == (120, 60)
    assert out.name == "reporting"


def test_apply_overrides_ignores_unrelated_policy():
    base = Policy("reporting", 60, 60)
    out = apply_overrides(base, {"export": {"limit": 5}})
    assert out == base


def test_apply_overrides_partial_limit_only():
    base = Policy("reporting", 60, 60)
    out = apply_overrides(base, {"reporting": {"limit": 90}})
    assert (out.limit, out.window_seconds) == (90, 60)
