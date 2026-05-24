"""JWT key management API.

Public (no auth):
    GET  /.well-known/jwks.json   — JWK Set for external token verification

Superuser-only (platform auth dependency):
    GET  /platform/jwt-keys/       — list all non-deleted signing keys
"""
from __future__ import annotations

import base64
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.core.db import get_platform_session
from app.modules.iam.keys.models import JwtSigningKey
from app.modules.iam.keys.schemas import JwkOut, JwksResponse, JwtKeyOut

_log = structlog.get_logger(__name__)

# Public — mounted at app root so the path is exactly /.well-known/jwks.json.
jwks_router = APIRouter(tags=["jwks"])

# Superuser admin endpoints.
key_mgmt_router = APIRouter(prefix="/platform/jwt-keys", tags=["platform-jwt-keys"])

PlatformSession = Annotated["AsyncSession", Depends(get_platform_session)]


def _rsa_pem_to_jwk(kid: str, public_key_pem: str, algorithm: str) -> JwkOut:
    """Convert an RSA public key PEM to a JWK dict."""
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    raw_key = load_pem_public_key(public_key_pem.encode())
    if not isinstance(raw_key, RSAPublicKey):
        raise ValueError(f"Expected RSA public key, got {type(raw_key).__name__}")
    numbers = raw_key.public_numbers()
    key_size_bytes = (raw_key.key_size + 7) // 8

    def _b64url(n: int, byte_length: int) -> str:
        return (
            base64.urlsafe_b64encode(n.to_bytes(byte_length, "big"))
            .rstrip(b"=")
            .decode()
        )

    return JwkOut(
        kid=kid,
        alg=algorithm,
        n=_b64url(numbers.n, key_size_bytes),
        e=_b64url(numbers.e, 3),
    )


@jwks_router.get("/.well-known/jwks.json", response_model=JwksResponse)
async def get_jwks(session: PlatformSession) -> JwksResponse:
    """Return active and retiring public keys in JWK Set format.

    Public endpoint — no authentication required.
    Returns an empty ``keys`` list when no signing keys exist yet.
    """
    result = await session.execute(
        select(JwtSigningKey)
        .where(JwtSigningKey.status.in_(["active", "retiring"]))
        .where(JwtSigningKey.deleted_at.is_(None))
        .order_by(JwtSigningKey.created_at.desc())
    )
    keys = result.scalars().all()

    jwks: list[JwkOut] = []
    for key in keys:
        if key.algorithm == "RS256":
            jwks.append(_rsa_pem_to_jwk(key.kid, key.public_key, key.algorithm))
        # EdDSA support: add here in a future plan when EdDSA keys are introduced.

    return JwksResponse(keys=jwks)


@key_mgmt_router.get("/", response_model=list[JwtKeyOut])
async def list_jwt_keys(session: PlatformSession) -> list[JwtKeyOut]:
    """List all non-deleted signing keys. Requires superuser.

    When ``PLATFORM_AUTH_MODE`` is flipped to ``jwt`` in plan 09, the
    ``get_current_superuser`` dependency will enforce real JWT verification.
    Until then the stub enforces UUID validity and active status.
    """
    result = await session.execute(
        select(JwtSigningKey)
        .where(JwtSigningKey.deleted_at.is_(None))
        .order_by(JwtSigningKey.created_at.desc())
    )
    signing_keys = result.scalars().all()
    return [JwtKeyOut.model_validate(k) for k in signing_keys]
