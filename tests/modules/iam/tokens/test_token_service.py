import uuid

import pytest

from app.modules.iam.tokens.service import (
    decode_token,
    encode_access_token,
    encode_refresh_token,
    get_unverified_kid,
)


def _make_rsa_keypair() -> tuple[bytes, bytes, str]:
    """Generate a test RSA keypair. Returns (private_pem, public_pem, kid)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem, "test-kid-001"


@pytest.fixture()
def rsa_keypair() -> tuple[bytes, bytes, str]:
    return _make_rsa_keypair()


def test_encode_access_token_produces_three_part_jwt(rsa_keypair):
    private_pem, _, kid = rsa_keypair
    token = encode_access_token(
        sub=str(uuid.uuid4()),
        audience="platform",
        session_id=str(uuid.uuid4()),
        actor_type="platform_user",
        kid=kid,
        private_key_pem=private_pem,
        algorithm="RS256",
        ttl_seconds=900,
    )
    assert isinstance(token, str)
    assert token.count(".") == 2


def test_decode_access_token_returns_all_expected_claims(rsa_keypair):
    private_pem, public_pem, kid = rsa_keypair
    subject = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    token = encode_access_token(
        sub=subject,
        audience="platform",
        session_id=session_id,
        actor_type="platform_user",
        kid=kid,
        private_key_pem=private_pem,
        algorithm="RS256",
        ttl_seconds=900,
    )
    claims = decode_token(
        token, audience="platform", public_key_pem=public_pem, algorithm="RS256"
    )

    assert claims["sub"] == subject
    assert claims["aud"] == "platform"
    assert claims["session_id"] == session_id
    assert claims["actor_type"] == "platform_user"
    assert claims["kid"] == kid
    assert "exp" in claims
    assert "iat" in claims
    assert "jti" in claims


def test_decode_token_with_wrong_audience_raises_value_error(rsa_keypair):
    private_pem, public_pem, kid = rsa_keypair
    token = encode_access_token(
        sub=str(uuid.uuid4()),
        audience="platform",
        session_id=str(uuid.uuid4()),
        actor_type="platform_user",
        kid=kid,
        private_key_pem=private_pem,
        algorithm="RS256",
        ttl_seconds=900,
    )
    with pytest.raises(ValueError, match="[Aa]udience"):
        decode_token(
            token, audience="tenant:acme", public_key_pem=public_pem, algorithm="RS256"
        )


def test_decode_expired_token_raises_value_error(rsa_keypair):
    private_pem, public_pem, kid = rsa_keypair
    token = encode_access_token(
        sub=str(uuid.uuid4()),
        audience="platform",
        session_id=str(uuid.uuid4()),
        actor_type="platform_user",
        kid=kid,
        private_key_pem=private_pem,
        algorithm="RS256",
        ttl_seconds=-1,  # already expired
    )
    with pytest.raises(ValueError, match="[Ee]xpir"):
        decode_token(
            token, audience="platform", public_key_pem=public_pem, algorithm="RS256"
        )


def test_decode_tampered_signature_raises_value_error(rsa_keypair):
    private_pem, public_pem, kid = rsa_keypair
    token = encode_access_token(
        sub=str(uuid.uuid4()),
        audience="platform",
        session_id=str(uuid.uuid4()),
        actor_type="platform_user",
        kid=kid,
        private_key_pem=private_pem,
        algorithm="RS256",
        ttl_seconds=900,
    )
    parts = token.split(".")
    tampered = parts[0] + "." + parts[1] + ".invalidsignatureXYZ"
    with pytest.raises(ValueError):
        decode_token(
            tampered, audience="platform", public_key_pem=public_pem, algorithm="RS256"
        )


def test_refresh_token_omits_actor_type_claim(rsa_keypair):
    import jwt as pyjwt

    private_pem, _, kid = rsa_keypair
    token = encode_refresh_token(
        sub=str(uuid.uuid4()),
        audience="platform",
        session_id=str(uuid.uuid4()),
        kid=kid,
        private_key_pem=private_pem,
        algorithm="RS256",
        ttl_seconds=3600,
    )
    payload = pyjwt.decode(token, options={"verify_signature": False}, algorithms=["RS256"])
    assert "sub" in payload
    assert "session_id" in payload
    assert "actor_type" not in payload


def test_each_token_gets_a_unique_jti(rsa_keypair):
    import jwt as pyjwt

    private_pem, _, kid = rsa_keypair
    tokens = [
        encode_access_token(
            sub=str(uuid.uuid4()),
            audience="platform",
            session_id=str(uuid.uuid4()),
            actor_type="platform_user",
            kid=kid,
            private_key_pem=private_pem,
            algorithm="RS256",
            ttl_seconds=900,
        )
        for _ in range(3)
    ]
    jtis = [
        pyjwt.decode(t, options={"verify_signature": False}, algorithms=["RS256"])["jti"]
        for t in tokens
    ]
    assert len(set(jtis)) == 3  # all unique


def test_get_unverified_kid_extracts_kid_from_header(rsa_keypair):
    private_pem, _, kid = rsa_keypair
    token = encode_access_token(
        sub=str(uuid.uuid4()),
        audience="platform",
        session_id=str(uuid.uuid4()),
        actor_type="platform_user",
        kid=kid,
        private_key_pem=private_pem,
        algorithm="RS256",
        ttl_seconds=900,
    )
    assert get_unverified_kid(token) == kid


def test_get_unverified_kid_raises_on_malformed_token():
    with pytest.raises(ValueError, match="Malformed"):
        get_unverified_kid("not.a.jwt")
