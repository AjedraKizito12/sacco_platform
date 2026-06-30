from __future__ import annotations

from sqlalchemy import Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SaccoKycRequirement(Base):
    """Platform-global override of a SACCO KYC field's required-ness.

    Override rows only: a missing row means "use the catalog default".
    Locked catalog fields ignore any row here. One row per field_key.
    """

    __tablename__ = "sacco_kyc_requirements"
    __table_args__ = {"schema": "platform"}

    field_key: Mapped[str] = mapped_column(Text, primary_key=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
