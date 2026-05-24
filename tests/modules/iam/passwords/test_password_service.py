"""Tests for the argon2id password hashing wrapper.

These tests intentionally use the real argon2id implementation (not mocked)
because the point of the module is correct password hashing. Each hash call
takes ~200–400 ms due to the OWASP-recommended parameters. This is expected
and acceptable — the test suite has ~6 tests here, adding ~2 s total.
"""
import pytest

from app.modules.iam.passwords.service import hash_password, needs_rehash, verify_password


def test_hash_is_not_plaintext():
    hashed = hash_password("CorrectHorseBatteryStaple!")
    assert hashed != "CorrectHorseBatteryStaple!"
    assert "CorrectHorseBatteryStaple" not in hashed


def test_hash_uses_argon2id_scheme():
    hashed = hash_password("CorrectHorseBatteryStaple!")
    # passlib argon2id hashes start with $argon2id$
    assert hashed.startswith("$argon2id$"), f"Unexpected prefix: {hashed[:30]}"


def test_hash_is_non_deterministic():
    # Two hashes of the same password must differ (random salt per call).
    h1 = hash_password("CorrectHorseBatteryStaple!")
    h2 = hash_password("CorrectHorseBatteryStaple!")
    assert h1 != h2


def test_verify_correct_password_returns_true():
    hashed = hash_password("CorrectHorseBatteryStaple!")
    assert verify_password("CorrectHorseBatteryStaple!", hashed) is True


def test_verify_wrong_password_returns_false():
    hashed = hash_password("CorrectHorseBatteryStaple!")
    assert verify_password("WrongPassword123!", hashed) is False


def test_hash_password_rejects_too_short_password():
    # Default minimum is 12 characters; "tooshort" has 8.
    with pytest.raises(ValueError, match="at least 12"):
        hash_password("tooshort")


def test_hash_password_accepts_exactly_minimum_length():
    # 12 characters — exactly at the boundary; must not raise.
    hashed = hash_password("A" * 12)
    assert verify_password("A" * 12, hashed) is True


def test_needs_rehash_returns_false_for_current_parameters():
    hashed = hash_password("CorrectHorseBatteryStaple!")
    # Hash was just produced with the current context — no rehash needed.
    assert needs_rehash(hashed) is False


def test_needs_rehash_returns_true_for_outdated_bcrypt_hash():
    # Simulate a legacy bcrypt hash that was in the DB before argon2id migration.
    # passlib can verify bcrypt, but needs_rehash will return True because
    # the CryptContext only accepts argon2 as non-deprecated.
    from passlib.hash import bcrypt

    legacy_hash = bcrypt.using(rounds=4).hash("CorrectHorseBatteryStaple!")
    # verify still works (passlib handles multiple schemes)
    assert verify_password("CorrectHorseBatteryStaple!", legacy_hash) is True
    # but rehash is needed
    assert needs_rehash(legacy_hash) is True
