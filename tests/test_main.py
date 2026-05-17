import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app, lifespan


@pytest.fixture
async def client() -> AsyncClient:
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def test_healthz_returns_200(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_healthz_is_fast_and_needs_no_deps(client: AsyncClient) -> None:
    """Liveness probe must never touch infra services."""
    # If this test passes without real infra running, the probe is truly cheap.
    response = await client.get("/healthz")
    assert response.status_code == 200


async def test_request_id_echoed_when_provided(client: AsyncClient) -> None:
    response = await client.get("/healthz", headers={"X-Request-ID": "my-trace-id"})
    assert response.headers.get("x-request-id") == "my-trace-id"


async def test_request_id_generated_when_absent(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    rid = response.headers.get("x-request-id")
    assert rid is not None
    # UUID4: 8-4-4-4-12 hex, 36 chars including dashes
    assert len(rid) == 36
    assert rid.count("-") == 4


async def test_unknown_route_returns_404(client: AsyncClient) -> None:
    response = await client.get("/does-not-exist")
    assert response.status_code == 404
