from httpx import ASGITransport, AsyncClient

from app.main import app, lifespan


async def test_readyz_includes_per_dependency_latency() -> None:
    # A bare ASGITransport(app=app) never runs lifespan, so app.state.redis is
    # unset and the handler crashes -- reuse the lifespan-aware pattern from
    # tests/test_main.py instead.
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/readyz")
    body = resp.json()
    assert "checks" in body
    # Each check now reports {status, latency_ms}. Don't assert status == "ok"
    # -- infra may be down in the test environment.
    for _name, check in body["checks"].items():
        assert "status" in check
        assert "latency_ms" in check
        assert isinstance(check["latency_ms"], int | float)
