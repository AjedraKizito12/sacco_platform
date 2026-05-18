from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

# Maps operation_type → async executor callable.
# Callable signature: (session: AsyncSession, payload: dict) -> dict
approval_registry: dict[str, Callable[..., Any]] = {}

# Maps operation_type → required permission string (used by API dependency).
operation_type_permissions: dict[str, str] = {}


def approval_executor(operation_type: str, *, required_permission: str = "") -> Any:
    """Decorator: register an async function as the executor for operation_type.

    Usage:
        @approval_executor("loan.disburse", required_permission="loans:approve")
        async def execute_loan_disburse(session: AsyncSession, payload: dict) -> dict:
            ...

    The decorated function is called inline when quorum is met.
    """
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        approval_registry[operation_type] = fn
        if required_permission:
            operation_type_permissions[operation_type] = required_permission
        return fn

    return decorator
