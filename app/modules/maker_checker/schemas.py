import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SubmitApprovalRequest(BaseModel):
    operation_type: str
    payload: dict[str, Any]
    required_approvals: int = 1
    expires_at: datetime | None = None


class ApprovalActionRequest(BaseModel):
    comment: str | None = None


class RejectRequest(BaseModel):
    reason: str | None = None


class ApprovalActionOut(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID
    action: str
    acted_at: datetime
    comment: str | None

    model_config = {"from_attributes": True}


class ApprovalRequestOut(BaseModel):
    id: uuid.UUID
    operation_type: str
    payload: dict[str, Any]
    requested_by: uuid.UUID
    requested_at: datetime
    required_approvals: int
    status: str
    expires_at: datetime | None
    executed_at: datetime | None
    execution_result: dict[str, Any] | None
    rejection_reason: str | None

    model_config = {"from_attributes": True}
