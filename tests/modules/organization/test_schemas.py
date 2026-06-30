from __future__ import annotations

from app.core.kyc.catalog import SACCO_KYC_CATALOG
from app.core.kyc.completion import compute_completion
from app.modules.organization.models import OrganizationProfile
from app.modules.organization.schemas import OrganizationKycOut


def test_organization_kyc_out_maps_values_and_completion() -> None:
    row = OrganizationProfile(legal_name="Umoja", tax_id="T-1")
    completion = compute_completion(
        {f.key: getattr(row, f.key, None) for f in SACCO_KYC_CATALOG},
        SACCO_KYC_CATALOG,
        {},
    )
    out = OrganizationKycOut.from_row_and_completion(row, completion)
    assert out.values.legal_name == "Umoja"
    assert out.values.tax_id == "T-1"
    assert out.verified is False
    assert out.completion.is_complete is False
    assert any(i.key == "legal_name" and i.present for i in out.completion.items)
