from __future__ import annotations

from app.core.kyc.schemas import (
    KycRequirementItemOut,
    KycRequirementsIn,
    KycRequirementsOut,
)

# Back-compat names used by app/platform_/kyc/api.py and its tests.
# Same classes, same wire shapes — the definitions moved to app.core.kyc.schemas
# so the members module can reuse them without cross-module imports.
SaccoKycRequirementItemOut = KycRequirementItemOut
SaccoKycRequirementsOut = KycRequirementsOut
SaccoKycRequirementsIn = KycRequirementsIn

__all__ = [
    "SaccoKycRequirementItemOut",
    "SaccoKycRequirementsIn",
    "SaccoKycRequirementsOut",
]
