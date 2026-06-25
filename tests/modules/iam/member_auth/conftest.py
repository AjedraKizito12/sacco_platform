"""Shared fixtures for member_auth integration tests.

Provides an RSA keypair + a KeyService stub (MagicMock) returning that keypair
for the "tenant" signing-key audience — matching how the tenant_auth tests mock
KeyService. The JWT aud claim is "member:<slug>"; the signing key column is
"tenant" (reused).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

TEST_TENANT_SCHEMA = "tenant_test"
TEST_SLUG = "test-tenant"


@pytest.fixture(scope="module")
def rsa_keypair() -> tuple[bytes, bytes]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


@pytest.fixture(scope="module")
def mock_key_service(rsa_keypair: tuple[bytes, bytes]) -> MagicMock:
    """KeyService stub returning the test RSA keypair for the 'tenant' audience."""
    private_pem, public_pem = rsa_keypair
    ks = MagicMock()
    ks.get_active_signing_key = AsyncMock(
        return_value=("test-member-kid", private_pem, "RS256")
    )
    ks.get_verification_key = AsyncMock(return_value=(public_pem, "RS256", "tenant"))
    return ks
