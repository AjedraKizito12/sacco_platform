import base64
import os

import pytest

from app.modules.iam.keys.crypto import decrypt_private_key, encrypt_private_key, validate_kek


def test_encrypt_decrypt_round_trip():
    kek = os.urandom(32)
    pem = b"-----BEGIN PRIVATE KEY-----\nfakekey\n-----END PRIVATE KEY-----\n"
    ciphertext, nonce, tag = encrypt_private_key(pem, kek)
    recovered = decrypt_private_key(ciphertext, nonce, tag, kek)
    assert recovered == pem


def test_nonce_is_unique_per_call():
    kek = os.urandom(32)
    pem = b"same-data"
    _, nonce1, _ = encrypt_private_key(pem, kek)
    _, nonce2, _ = encrypt_private_key(pem, kek)
    assert nonce1 != nonce2


def test_wrong_kek_raises_value_error():
    kek = os.urandom(32)
    wrong_kek = os.urandom(32)
    pem = b"secret"
    ciphertext, nonce, tag = encrypt_private_key(pem, kek)
    with pytest.raises(ValueError, match="Decryption failed"):
        decrypt_private_key(ciphertext, nonce, tag, wrong_kek)


def test_tampered_ciphertext_raises_value_error():
    kek = os.urandom(32)
    pem = b"secret"
    ciphertext, nonce, tag = encrypt_private_key(pem, kek)
    bad = bytes([ciphertext[0] ^ 0xFF]) + ciphertext[1:]
    with pytest.raises(ValueError, match="Decryption failed"):
        decrypt_private_key(bad, nonce, tag, kek)


def test_validate_kek_accepts_valid_32_byte_b64():
    raw = os.urandom(32)
    result = validate_kek(base64.b64encode(raw).decode())
    assert result == raw
    assert len(result) == 32


def test_validate_kek_rejects_wrong_decoded_length():
    with pytest.raises(ValueError, match="32 bytes"):
        validate_kek(base64.b64encode(b"tooshort").decode())


def test_validate_kek_rejects_invalid_base64():
    with pytest.raises(ValueError, match="base64"):
        validate_kek("!!!not-valid!!!")
