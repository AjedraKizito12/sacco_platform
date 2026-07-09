from __future__ import annotations

from app.core.kyc.catalog import MEMBER_KYC_CATALOG
from app.core.kyc.completion import compute_completion
from app.core.kyc.schemas import KycCompletionOut, KycRequirementsIn, KycRequirementsOut


def test_completion_out_mirrors_computation() -> None:
    completion = compute_completion(
        {spec.key: None for spec in MEMBER_KYC_CATALOG},
        MEMBER_KYC_CATALOG,
        {},
    )
    out = KycCompletionOut.from_completion(completion)
    assert out.required_total == completion.required_total
    assert out.is_complete is False
    assert len(out.items) == len(MEMBER_KYC_CATALOG)


def test_requirements_out_from_config_preserves_order_and_locks() -> None:
    config = [(spec, spec.locked or spec.default_required) for spec in MEMBER_KYC_CATALOG]
    out = KycRequirementsOut.from_config(config)
    assert [i.key for i in out.items] == [s.key for s in MEMBER_KYC_CATALOG]
    assert out.items[0].locked is True  # full_name


def test_requirements_in_shape() -> None:
    body = KycRequirementsIn(required={"phone": False})
    assert body.required == {"phone": False}


def test_backcompat_reexports() -> None:
    # Existing import sites must keep working after the hoist.
    from app.modules.organization.schemas import KycCompletionOut as OrgAlias
    from app.platform_.kyc.schemas import SaccoKycRequirementsOut

    assert OrgAlias is KycCompletionOut
    assert SaccoKycRequirementsOut is KycRequirementsOut
