from __future__ import annotations

from app.core.kyc.catalog import FieldSpec
from app.core.kyc.completion import compute_completion

CATALOG = (
    FieldSpec("a", "A", locked=True, default_required=True),
    FieldSpec("b", "B", locked=False, default_required=True),
    FieldSpec("c", "C", locked=False, default_required=False),
)


def test_locked_field_is_always_required_even_if_override_false() -> None:
    result = compute_completion({"a": None, "b": "x", "c": "y"}, CATALOG, {"a": False})
    a = next(i for i in result.items if i.key == "a")
    assert a.required is True
    assert a.present is False
    assert "a" in result.missing_required
    assert result.is_complete is False


def test_override_makes_default_required_field_optional() -> None:
    # b default-required, overridden off → not counted as missing
    result = compute_completion({"a": "x", "b": None, "c": None}, CATALOG, {"b": False})
    assert result.missing_required == ()
    assert result.is_complete is True
    assert result.percent == 100


def test_blank_string_is_not_present() -> None:
    result = compute_completion({"a": "   ", "b": "x", "c": None}, CATALOG, {})
    a = next(i for i in result.items if i.key == "a")
    assert a.present is False
    assert "a" in result.missing_required


def test_percent_and_counts() -> None:
    # required: a (locked) + b (default) = 2; present required: a only
    result = compute_completion({"a": "x", "b": None, "c": None}, CATALOG, {})
    assert result.required_total == 2
    assert result.required_present == 1
    assert result.percent == 50
    assert result.is_complete is False


def test_no_required_fields_is_100_percent() -> None:
    catalog = (FieldSpec("a", "A", locked=False, default_required=False),)
    result = compute_completion({"a": None}, catalog, {})
    assert result.required_total == 0
    assert result.percent == 100
    assert result.is_complete is True


def test_unknown_override_keys_are_ignored() -> None:
    result = compute_completion({"a": "x", "b": "y", "c": None}, CATALOG, {"zzz": True})
    assert result.is_complete is True


def test_zero_is_present() -> None:
    catalog = (FieldSpec("n", "N", locked=True, default_required=True),)
    result = compute_completion({"n": 0}, catalog, {})
    n = next(i for i in result.items if i.key == "n")
    assert n.present is True
