from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSpec:
    """One KYC field in a catalog.

    locked: always required; cannot be toggled off (the hard minimums).
    default_required: the required-ness when no config override is present
        (only consulted for non-locked fields).
    """

    key: str
    label: str
    locked: bool
    default_required: bool


SACCO_KYC_CATALOG: tuple[FieldSpec, ...] = (
    FieldSpec("legal_name", "Registered legal name", locked=True, default_required=True),
    FieldSpec("registration_number", "Registration number", locked=True, default_required=True),
    FieldSpec("registered_address", "Registered physical address", locked=True, default_required=True),
    FieldSpec("primary_contact_name", "Primary contact name", locked=True, default_required=True),
    FieldSpec("primary_contact_email", "Primary contact email", locked=True, default_required=True),
    FieldSpec("registration_date", "Date of registration", locked=False, default_required=True),
    FieldSpec("regulator_name", "Regulator", locked=False, default_required=True),
    FieldSpec("license_number", "License number", locked=False, default_required=True),
    FieldSpec("tax_id", "Tax identification number", locked=False, default_required=True),
    FieldSpec("primary_contact_phone", "Primary contact phone", locked=False, default_required=True),
    FieldSpec("postal_address", "Postal address", locked=False, default_required=True),
    FieldSpec("district_region", "District / region", locked=False, default_required=True),
    FieldSpec("country", "Country", locked=False, default_required=True),
)


MEMBER_KYC_CATALOG: tuple[FieldSpec, ...] = (
    FieldSpec("full_name", "Full name", locked=True, default_required=True),
    FieldSpec("date_of_birth", "Date of birth", locked=True, default_required=True),
    FieldSpec("gender", "Gender", locked=True, default_required=True),
    FieldSpec("phone", "Phone", locked=False, default_required=True),
    FieldSpec("email", "Email", locked=False, default_required=True),
    FieldSpec("physical_address", "Physical address", locked=False, default_required=True),
    FieldSpec("national_id_number", "National ID number", locked=False, default_required=True),
    FieldSpec("id_document_type", "ID document type", locked=False, default_required=True),
    FieldSpec("id_document_number", "ID document number", locked=False, default_required=True),
    FieldSpec("id_issued_date", "ID issued date", locked=False, default_required=False),
    FieldSpec("id_expiry_date", "ID expiry date", locked=False, default_required=False),
    FieldSpec("next_of_kin_name", "Next of kin name", locked=False, default_required=True),
    FieldSpec("next_of_kin_phone", "Next of kin phone", locked=False, default_required=True),
    FieldSpec("occupation", "Occupation", locked=False, default_required=False),
)
