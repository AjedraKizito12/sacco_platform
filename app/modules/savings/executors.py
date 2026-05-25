"""Maker-checker executors for savings withdrawal operations.

Import this module at app startup to register executors in approval_registry.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.modules.maker_checker.registry import approval_executor

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@approval_executor("savings.withdraw")
async def execute_withdraw(session: AsyncSession, payload: dict) -> dict:
    raise NotImplementedError("savings.withdraw executor not yet implemented")
