"""Create platform.jwt_signing_keys; bootstrap initial RS256 keypairs.

Revision: 003
Depends on: 002 (platform_users must exist before adding created_by reference)

Bootstrap behaviour:
    Reads JWT_KEK from env. Fails with RuntimeError if absent or invalid.
    Generates one RS256-2048 keypair per audience ('platform', 'tenant').
    Inserts each as status='active'. Idempotent: skips if the target kid
    already exists in the table.
"""
from __future__ import annotations

import base64
import os
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def _get_kek() -> bytes:
    kek_b64 = os.environ.get("JWT_KEK", "")
    if not kek_b64:
        raise RuntimeError(
            "JWT_KEK environment variable is required to run migration 003. "
            "Generate one: python -c \"import os,base64; print(base64.b64encode(os.urandom(32)).decode())\""
        )
    try:
        kek = base64.b64decode(kek_b64, validate=True)
    except Exception as exc:
        raise RuntimeError("JWT_KEK is not valid base64") from exc
    if len(kek) != 32:
        raise RuntimeError(
            f"JWT_KEK must decode to exactly 32 bytes; got {len(kek)}"
        )
    return kek


def _generate_rs256_keypair() -> tuple[bytes, bytes]:
    """Return (private_key_pem, public_key_pem)."""
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
    return private_pem, public_pem


def _aes_gcm_encrypt(pem: bytes, kek: bytes) -> tuple[bytes, bytes, bytes]:
    """Return (ciphertext, nonce, tag). Inline copy — avoids importing app code in migrations."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    aesgcm = AESGCM(kek)
    ct_with_tag = aesgcm.encrypt(nonce, pem, None)
    return ct_with_tag[:-16], nonce, ct_with_tag[-16:]


def upgrade() -> None:
    op.create_table(
        "jwt_signing_keys",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("kid", sa.Text(), nullable=False),
        sa.Column("algorithm", sa.Text(), nullable=False),
        sa.Column("audience", sa.Text(), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("private_key_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("private_key_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("private_key_tag", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("activated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("retired_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'retiring', 'retired')",
            name="ck_jwt_signing_keys_status",
        ),
        sa.CheckConstraint(
            "algorithm IN ('RS256', 'EdDSA')",
            name="ck_jwt_signing_keys_algorithm",
        ),
        sa.CheckConstraint(
            "audience IN ('platform', 'tenant')",
            name="ck_jwt_signing_keys_audience",
        ),
        sa.UniqueConstraint("kid", name="uq_jwt_signing_keys_kid"),
        schema="platform",
    )
    op.create_index(
        "uq_jwt_signing_keys_active_per_audience",
        "jwt_signing_keys",
        ["audience"],
        unique=True,
        schema="platform",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_jwt_signing_keys_kid",
        "jwt_signing_keys",
        ["kid"],
        schema="platform",
    )

    # Bootstrap: one active keypair per audience (idempotent).
    kek = _get_kek()
    conn = op.get_bind()
    now = datetime.now(UTC)

    for audience in ("platform", "tenant"):
        kid = f"{audience}-2026-001"

        existing = conn.execute(
            sa.text("SELECT id FROM platform.jwt_signing_keys WHERE kid = :kid"),
            {"kid": kid},
        ).fetchone()
        if existing:
            continue

        private_pem, public_pem = _generate_rs256_keypair()
        ciphertext, nonce, tag = _aes_gcm_encrypt(private_pem, kek)

        conn.execute(
            sa.text(
                """
                INSERT INTO platform.jwt_signing_keys
                    (kid, algorithm, audience, public_key,
                     private_key_encrypted, private_key_nonce, private_key_tag,
                     status, created_at, activated_at)
                VALUES
                    (:kid, 'RS256', :audience, :public_key,
                     :ciphertext, :nonce, :tag,
                     'active', :now, :now)
                """
            ),
            {
                "kid": kid,
                "audience": audience,
                "public_key": public_pem.decode(),
                "ciphertext": ciphertext,
                "nonce": nonce,
                "tag": tag,
                "now": now,
            },
        )


def downgrade() -> None:
    op.drop_index(
        "uq_jwt_signing_keys_active_per_audience",
        table_name="jwt_signing_keys",
        schema="platform",
    )
    op.drop_index(
        "ix_jwt_signing_keys_kid",
        table_name="jwt_signing_keys",
        schema="platform",
    )
    op.drop_table("jwt_signing_keys", schema="platform")
