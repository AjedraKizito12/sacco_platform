from __future__ import annotations

from app.modules.iam.sessions.models import MemberSession
from app.modules.members.models import Member


def test_member_has_auth_columns() -> None:
    cols = Member.__table__.columns
    assert "hashed_password" in cols
    assert cols["hashed_password"].nullable is True
    assert "portal_enabled" in cols
    assert cols["portal_enabled"].nullable is False
    assert "last_login_at" in cols


def test_member_session_table_shape() -> None:
    assert MemberSession.__tablename__ == "member_sessions"
    # Tenant-schema table: no explicit schema (resolved via search_path).
    assert MemberSession.__table__.schema is None
    cols = MemberSession.__table__.columns
    for name in (
        "id",
        "member_id",
        "jti",
        "user_agent",
        "ip_address",
        "created_at",
        "expires_at",
        "revoked_at",
        "last_used_at",
    ):
        assert name in cols
