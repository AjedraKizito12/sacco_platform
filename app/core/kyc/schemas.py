"""Shared KYC wire schemas (pure — no DB, no I/O, per the core-tracker contract).

Consumed by the organization module (SACCO org KYC), platform_ KYC config,
and the members module (member KYC). Entity-specific response envelopes
stay in their modules; the completion/requirements shapes live here once.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.core.kyc.catalog import FieldSpec
from app.core.kyc.completion import KycCompletion


class KycFieldStatusOut(BaseModel):
    key: str
    label: str
    required: bool
    present: bool


class KycCompletionOut(BaseModel):
    items: list[KycFieldStatusOut]
    required_total: int
    required_present: int
    percent: int
    missing_required: list[str]
    is_complete: bool

    @classmethod
    def from_completion(cls, c: KycCompletion) -> KycCompletionOut:
        return cls(
            items=[
                KycFieldStatusOut(
                    key=i.key, label=i.label, required=i.required, present=i.present
                )
                for i in c.items
            ],
            required_total=c.required_total,
            required_present=c.required_present,
            percent=c.percent,
            missing_required=list(c.missing_required),
            is_complete=c.is_complete,
        )


class KycRequirementItemOut(BaseModel):
    key: str
    label: str
    locked: bool
    required: bool


class KycRequirementsOut(BaseModel):
    items: list[KycRequirementItemOut]

    @classmethod
    def from_config(cls, config: list[tuple[FieldSpec, bool]]) -> KycRequirementsOut:
        return cls(
            items=[
                KycRequirementItemOut(
                    key=spec.key, label=spec.label, locked=spec.locked, required=required
                )
                for spec, required in config
            ]
        )


class KycRequirementsIn(BaseModel):
    """Map of field_key → required. Locked/unknown keys are ignored server-side."""

    required: dict[str, bool]
