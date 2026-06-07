import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Any

import aio_pika
import structlog
from elasticsearch import AsyncElasticsearch
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.db import engine
from app.modules.credit import executors as _credit_executors  # noqa: F401
from app.modules.credit.api import router as credit_router
from app.modules.fees.api import router as fees_router
from app.modules.iam.keys.api import jwks_router, key_mgmt_router
from app.modules.iam.platform_auth.api import router as platform_auth_router
from app.modules.iam.tenant_auth.api import router as tenant_auth_router
from app.modules.ledger import executors as _ledger_executors  # noqa: F401
from app.modules.ledger.api import router as ledger_router
from app.modules.maker_checker.api import router as maker_checker_router
from app.modules.maker_checker.platform_api import router as platform_maker_checker_router
from app.modules.members import executors as _members_executors  # noqa: F401
from app.modules.members.api import router as members_router
from app.modules.reporting.api import router as reporting_router
from app.modules.savings import executors as _savings_executors  # noqa: F401
from app.modules.savings.api import router as savings_router
from app.modules.shares import executors as _shares_executors  # noqa: F401
from app.modules.shares.api import router as shares_router
from app.platform_.auth import get_current_superuser
from app.platform_.billing import executors as _billing_executors  # noqa: F401
from app.platform_.billing.api import (
    platform_router as billing_platform_router,
)
from app.platform_.billing.api import (
    tenant_router as billing_tenant_router,
)
from app.platform_.impersonations import executors as _impersonation_executors  # noqa: F401
from app.platform_.impersonations.api import router as impersonations_router
from app.platform_.tenant_users_admin.api import (
    router as tenant_users_admin_router,
)
from app.platform_.tenants import executors as _tenants_executors  # noqa: F401
from app.platform_.tenants.api import router as platform_tenants_router
from app.platform_.users.api import router as platform_users_router

settings = get_settings()


def _configure_logging() -> None:
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
    ]
    if settings.structlog_json:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            structlog.stdlib.NAME_TO_LEVEL[settings.log_level.lower()]  # type: ignore[attr-defined]
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


_configure_logging()
_log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=False)

    # Refuse stub auth in production.
    if settings.app_env == "production" and settings.platform_auth_mode == "stub":
        raise RuntimeError(
            "Refusing to boot: PLATFORM_AUTH_MODE=stub is forbidden in production. "
            "Set PLATFORM_AUTH_MODE=jwt when IAM ships."
        )
    if settings.app_env == "production" and settings.tenant_auth_mode == "stub":
        raise RuntimeError(
            "Refusing to boot: TENANT_AUTH_MODE=stub is forbidden in production. "
            "Set TENANT_AUTH_MODE=jwt when IAM ships."
        )

    # Verify active signing keys exist when JWT auth is enabled.
    if settings.platform_auth_mode == "jwt" or settings.tenant_auth_mode == "jwt":
        from app.modules.iam.keys.service import verify_boot_keys
        await verify_boot_keys()

    _log.info("Startup complete", env=settings.app_env)
    yield
    await app.state.redis.aclose()
    await engine.dispose()
    _log.info("Shutdown complete")


app: FastAPI = FastAPI(title="SACCO Platform API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next: Any) -> Any:
    request_id = request.headers.get(settings.request_id_header) or str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(request_id=request_id)
    response = await call_next(request)
    response.headers[settings.request_id_header] = request_id
    structlog.contextvars.clear_contextvars()
    return response


app.include_router(maker_checker_router)
app.include_router(platform_maker_checker_router)
app.include_router(ledger_router)
app.include_router(members_router)
app.include_router(shares_router)
app.include_router(savings_router)
app.include_router(credit_router)
app.include_router(fees_router)
app.include_router(reporting_router)
app.include_router(platform_auth_router)
app.include_router(tenant_auth_router)
app.include_router(billing_platform_router)
app.include_router(billing_tenant_router)
app.include_router(platform_tenants_router)
app.include_router(platform_users_router)
app.include_router(impersonations_router)
app.include_router(tenant_users_admin_router)
app.include_router(jwks_router)
app.include_router(
    key_mgmt_router,
    dependencies=[Depends(get_current_superuser)],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    _log.exception("Unhandled exception", path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "internal server error"},
    )


# ── Health endpoints ──────────────────────────────────────────────────────────


@app.get("/healthz", tags=["ops"])
async def healthz() -> dict[str, str]:
    """Liveness probe — returns 200 immediately without touching dependencies."""
    return {"status": "ok"}


async def _check_postgres() -> str:
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        return f"error: {exc}"


async def _check_redis(redis_client: Redis) -> str:
    try:
        await redis_client.ping()
        return "ok"
    except Exception as exc:
        return f"error: {exc}"


async def _check_rabbitmq() -> str:
    try:
        conn = await asyncio.wait_for(
            aio_pika.connect_robust(settings.rabbitmq_url),
            timeout=3.0,
        )
        await conn.close()
        return "ok"
    except Exception as exc:
        return f"error: {exc}"


async def _check_elasticsearch() -> str:
    es = AsyncElasticsearch(settings.elasticsearch_url)
    try:
        await asyncio.wait_for(es.cluster.health(), timeout=3.0)
        return "ok"
    except Exception as exc:
        return f"error: {exc}"
    finally:
        await es.close()


@app.get("/readyz", tags=["ops"])
async def readyz(request: Request) -> JSONResponse:
    """Readiness probe — checks all four infra dependencies concurrently."""
    postgres, redis, rabbitmq, elasticsearch = await asyncio.gather(
        _check_postgres(),
        _check_redis(request.app.state.redis),
        _check_rabbitmq(),
        _check_elasticsearch(),
    )
    checks = {
        "postgres": postgres,
        "redis": redis,
        "rabbitmq": rabbitmq,
        "elasticsearch": elasticsearch,
    }
    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "ok" if all_ok else "degraded", "checks": checks},
    )
