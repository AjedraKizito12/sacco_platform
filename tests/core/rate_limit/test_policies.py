from app.core.rate_limit.policies import match_policy


def test_anonymous_login_is_10_per_min():
    p = match_policy("/auth/token", "anonymous")
    assert (p.name, p.limit, p.window_seconds) == ("auth_login", 10, 60)


def test_anonymous_password_reset_is_3_per_15min():
    p = match_policy("/member/auth/password-reset/request", "anonymous")
    assert (p.limit, p.window_seconds) == (3, 900)


def test_reporting_is_60_per_min_for_tenant():
    assert match_policy("/reporting/loan-portfolio", "tenant").limit == 60


def test_statement_export_is_10_per_min():
    assert match_policy("/member/statement", "member").limit == 10


def test_platform_admin_is_600_per_min():
    assert match_policy("/platform/tenants", "platform").limit == 600


def test_authenticated_default_is_300_per_min():
    assert match_policy("/savings/accounts", "tenant").name == "authenticated_default"


def test_anonymous_default_catch_all():
    # an anonymous hit to a non-auth path still gets a bucket
    assert match_policy("/savings/accounts", "anonymous").name == "anonymous_default"
