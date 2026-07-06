from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.core.kyc.catalog import FieldSpec


@dataclass(frozen=True)
class FieldStatus:
    key: str
    label: str
    required: bool
    present: bool


@dataclass(frozen=True)
class KycCompletion:
    items: tuple[FieldStatus, ...]
    required_total: int
    required_present: int
    percent: int
    missing_required: tuple[str, ...]
    is_complete: bool


def _is_present(value: object | None) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


def _effective_required(spec: FieldSpec, overrides: Mapping[str, bool]) -> bool:
    if spec.locked:
        return True
    return overrides.get(spec.key, spec.default_required)


def compute_completion(
    values: Mapping[str, object | None],
    catalog: Sequence[FieldSpec],
    required_overrides: Mapping[str, bool],
) -> KycCompletion:
    """Compute KYC completion for an entity.

    Pure function. ``required_overrides`` only affects non-locked fields;
    unknown keys are ignored. A field is "present" when its value is not None
    and, for strings, non-blank.
    """
    items: list[FieldStatus] = []
    missing: list[str] = []
    required_total = 0
    required_present = 0

    for spec in catalog:
        required = _effective_required(spec, required_overrides)
        present = _is_present(values.get(spec.key))
        items.append(
            FieldStatus(key=spec.key, label=spec.label, required=required, present=present)
        )
        if required:
            required_total += 1
            if present:
                required_present += 1
            else:
                missing.append(spec.key)

    percent = 100 if required_total == 0 else round(required_present / required_total * 100)

    return KycCompletion(
        items=tuple(items),
        required_total=required_total,
        required_present=required_present,
        percent=percent,
        missing_required=tuple(missing),
        is_complete=not missing,
    )
