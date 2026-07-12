"""State for the search reconcile beat (platform schema).

One row per (index_name, scope): scope is a tenant schema_name for
tenant-owned entities, or 'platform' for platform entities.
"""
from __future__ import annotations

from datetime import datetime  # noqa: TC003

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SearchIndexState(Base):
    __tablename__ = "search_index_state"
    __table_args__ = {"schema": "platform"}

    index_name: Mapped[str] = mapped_column(Text, primary_key=True)
    scope: Mapped[str] = mapped_column(Text, primary_key=True)
    last_watermark: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
