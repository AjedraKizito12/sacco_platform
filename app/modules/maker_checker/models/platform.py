from __future__ import annotations

import uuid  # noqa: TC003 (uuid.UUID used in Mapped[] and as column type at runtime)

from sqlalchemy import UUID, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.maker_checker.models.mixins import ApprovalActionMixin, ApprovalRequestMixin


class PlatformApprovalRequest(ApprovalRequestMixin, Base):
    __tablename__ = "approval_requests"
    __table_args__ = {"schema": "platform"}


class PlatformApprovalAction(ApprovalActionMixin, Base):
    __tablename__ = "approval_actions"
    __table_args__ = (
        UniqueConstraint(
            "approval_request_id",
            "actor_user_id",
            name="uq_platform_approval_actions_no_double_vote",
        ),
        {"schema": "platform"},
    )
    approval_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.approval_requests.id"),
        nullable=False,
    )
