from app.core.search.registry import platform_indices, resolve_indices, tenant_indices


def test_tenant_default_is_all_tenant_indices():
    assert set(resolve_indices("tenant", None)) == set(tenant_indices())


def test_types_narrows_within_audience():
    got = resolve_indices("tenant", "member,loan")
    assert set(got) == {"sacco_members", "sacco_loans"}


def test_foreign_type_is_ignored_not_honored():
    # a tenant caller naming a platform type gets none of it
    got = resolve_indices("tenant", "invoice,member")
    assert got == ["sacco_members"]


def test_platform_default_excludes_tenant_indices():
    assert "sacco_members" not in platform_indices()
