from app.modules.maker_checker.registry import (
    approval_executor,
    approval_registry,
    operation_type_permissions,
)


def test_approval_executor_registers_function():
    @approval_executor("test.noop", required_permission="test:approve")
    async def _noop(session, payload):
        return {}

    assert "test.noop" in approval_registry
    assert approval_registry["test.noop"] is _noop
    assert operation_type_permissions["test.noop"] == "test:approve"


def test_approval_executor_without_permission():
    @approval_executor("test.noop2")
    async def _noop2(session, payload):
        return {}

    assert "test.noop2" in approval_registry
    assert "test.noop2" not in operation_type_permissions
