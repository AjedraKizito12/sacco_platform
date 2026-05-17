import pytest

from app.core.db import _SCHEMA_RE, _SLUG_RE


@pytest.mark.parametrize(
    "slug, valid",
    [
        ("acme", True),
        ("acme-corp", True),
        ("a1b2c3", True),
        ("a" * 40, True),
        ("a" * 41, False),   # too long
        ("ACME", False),     # uppercase
        ("acme_corp", False),  # underscore not allowed in slug
        ("acme corp", False),  # space
        ("", False),           # empty
        ("-acme", True),       # leading dash is valid per regex
        ("acme-", True),       # trailing dash is valid per regex
    ],
)
def test_slug_regex(slug: str, valid: bool) -> None:
    assert bool(_SLUG_RE.match(slug)) == valid


@pytest.mark.parametrize(
    "schema, valid",
    [
        ("tenant_acme", True),
        ("tenant_acme_corp", True),
        ("tenant_a1b2", True),
        ("tenant_" + "a" * 40, True),
        ("tenant_" + "a" * 41, False),  # too long
        ("platform", False),             # must start with tenant_
        ("public", False),
        ("tenant_ACME", False),          # uppercase not allowed
        ("tenantacme", False),           # missing underscore separator
        ("tenant_", False),              # empty suffix (length 0 after tenant_)
    ],
)
def test_schema_name_regex(schema: str, valid: bool) -> None:
    assert bool(_SCHEMA_RE.match(schema)) == valid
