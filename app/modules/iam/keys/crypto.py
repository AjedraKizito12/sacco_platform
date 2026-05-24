"""AES-256-GCM envelope encryption for JWT signing private keys.

The private key PEM is encrypted under a Key Encryption Key (KEK) supplied as
a base64-encoded 32-byte value from the ``JWT_KEK`` environment variable.

Each encryption call generates a fresh 12-byte nonce (GCM-recommended length).
The 16-byte GCM authentication tag is returned separately so it can be stored
in its own BYTEA column on the jwt_signing_keys table.
"""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def encrypt_private_key(pem: bytes, kek: bytes) -> tuple[bytes, bytes, bytes]:
    """Encrypt *pem* under *kek* using AES-256-GCM.

    Returns ``(ciphertext, nonce, tag)`` — three separate byte strings
    suitable for storing in dedicated BYTEA columns.

    The ``cryptography`` library appends the 16-byte GCM auth tag to the
    ciphertext. This function splits them so callers can store them
    independently and avoid having to know the internal layout.
    """
    nonce = os.urandom(12)
    aesgcm = AESGCM(kek)
    ct_with_tag = aesgcm.encrypt(nonce, pem, None)
    ciphertext = ct_with_tag[:-16]
    tag = ct_with_tag[-16:]
    return ciphertext, nonce, tag


def decrypt_private_key(
    ciphertext: bytes,
    nonce: bytes,
    tag: bytes,
    kek: bytes,
) -> bytes:
    """Decrypt *ciphertext* using *kek*, verifying the GCM auth *tag*.

    Raises ``ValueError`` if the tag does not match (wrong KEK or corrupted
    ciphertext). The error message is deliberately generic to avoid leaking
    information about whether the KEK or the ciphertext is wrong.
    """
    aesgcm = AESGCM(kek)
    ct_with_tag = ciphertext + tag
    try:
        return aesgcm.decrypt(nonce, ct_with_tag, None)
    except Exception as exc:
        raise ValueError("Decryption failed: invalid KEK or corrupted data") from exc


def validate_kek(kek_b64: str) -> bytes:
    """Decode and validate a base64-encoded KEK string.

    Returns the raw 32-byte key. Raises ``ValueError`` if the string is not
    valid base64 or does not decode to exactly 32 bytes.
    """
    try:
        kek = base64.b64decode(kek_b64, validate=True)
    except Exception:
        raise ValueError("JWT_KEK must be valid base64") from None
    if len(kek) != 32:
        raise ValueError(
            f"JWT_KEK must decode to exactly 32 bytes; got {len(kek)}"
        )
    return kek
