from __future__ import annotations

from app.core.kyc.catalog import (
    MEMBER_KYC_CATALOG,
    SACCO_KYC_CATALOG,
    FieldSpec,
)


def test_sacco_catalog_keys_are_unique() -> None:
    keys = [f.key for f in SACCO_KYC_CATALOG]
    assert len(keys) == len(set(keys))


def test_sacco_locked_minimums() -> None:
    locked = {f.key for f in SACCO_KYC_CATALOG if f.locked}
    assert locked == {
        "legal_name",
        "registration_number",
        "registered_address",
        "primary_contact_name",
        "primary_contact_email",
    }


def test_sacco_toggleable_default_required() -> None:
    toggleable = {f.key for f in SACCO_KYC_CATALOG if not f.locked}
    assert toggleable == {
        "registration_date",
        "regulator_name",
        "license_number",
        "tax_id",
        "primary_contact_phone",
        "postal_address",
        "district_region",
        "country",
    }
    # every toggleable SACCO field defaults to required
    assert all(f.default_required for f in SACCO_KYC_CATALOG if not f.locked)


def test_member_locked_minimums_match_not_null_columns() -> None:
    locked = {f.key for f in MEMBER_KYC_CATALOG if f.locked}
    assert locked == {"full_name", "date_of_birth", "gender"}


def test_fieldspec_is_frozen() -> None:
    spec = FieldSpec(key="x", label="X", locked=False, default_required=True)
    try:
        spec.key = "y"  # type: ignore[misc]
    except Exception as exc:  # noqa: BLE001
        assert "cannot assign" in str(exc).lower() or "frozen" in str(exc).lower()
    else:
        raise AssertionError("FieldSpec must be frozen")
