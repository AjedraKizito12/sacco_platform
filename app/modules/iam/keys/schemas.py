"""Pydantic schemas for JWT key management responses."""
from __future__ import annotations

import uuid  # noqa: TC003 — used at runtime by Pydantic for field validation
from datetime import datetime  # noqa: TC003 — used at runtime by Pydantic for field validation

from pydantic import BaseModel


class JwkOut(BaseModel):
    """Single RSA public key in JWK format."""

    kty: str = "RSA"
    kid: str
    use: str = "sig"
    alg: str
    n: str  # RSA modulus, base64url-encoded
    e: str  # RSA public exponent, base64url-encoded


class JwksResponse(BaseModel):
    """JWK Set — returned by GET /.well-known/jwks.json."""

    keys: list[JwkOut]


class JwtKeyOut(BaseModel):
    """Admin view of a signing key row. No private key material."""

    id: uuid.UUID
    kid: str
    algorithm: str
    audience: str
    status: str
    created_at: datetime
    activated_at: datetime | None
    retired_at: datetime | None
    deleted_at: datetime | None

    model_config = {"from_attributes": True}
