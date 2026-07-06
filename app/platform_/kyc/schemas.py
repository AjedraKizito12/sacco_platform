from __future__ import annotations

from pydantic import BaseModel

from app.core.kyc.catalog import FieldSpec


class SaccoKycRequirementItemOut(BaseModel):
    key: str
    label: str
    locked: bool
    required: bool


class SaccoKycRequirementsOut(BaseModel):
    items: list[SaccoKycRequirementItemOut]

    @classmethod
    def from_config(cls, config: list[tuple[FieldSpec, bool]]) -> SaccoKycRequirementsOut:
        return cls(
            items=[
                SaccoKycRequirementItemOut(
                    key=spec.key, label=spec.label, locked=spec.locked, required=required
                )
                for spec, required in config
            ]
        )


class SaccoKycRequirementsIn(BaseModel):
    """Map of field_key → required. Locked/unknown keys are ignored server-side."""

    required: dict[str, bool]
