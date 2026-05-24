import base64
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # Elasticsearch
    elasticsearch_url: str = "http://localhost:9200"

    # App
    app_secret_key: str
    app_env: str = "development"
    log_level: str = "INFO"
    allowed_origins: list[str] = ["http://localhost:3000"]

    # DB pool
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Observability
    structlog_json: bool = False
    slow_query_ms: int = 200

    # Headers
    request_id_header: str = "X-Request-ID"
    tenant_header: str = "X-Tenant-Slug"

    # Outbox retention
    outbox_retention_days: int = 90

    # Platform auth
    platform_auth_mode: str = "stub"  # "stub" | "jwt"
    platform_bootstrap_email: str = ""
    platform_bootstrap_full_name: str = "Platform Admin"

    # Tenant auth
    tenant_auth_mode: str = "stub"  # "stub" | "jwt"

    # JWT signing key infrastructure
    jwt_kek: str = ""  # base64-encoded 32-byte key-encryption-key; required when auth_mode=jwt
    jwt_key_rotation_days: int = 90
    jwt_access_ttl_seconds: int = 900             # 15 min
    jwt_refresh_ttl_platform_seconds: int = 3600  # 1 h
    jwt_refresh_ttl_tenant_seconds: int = 28800   # 8 h

    @field_validator("jwt_kek")
    @classmethod
    def validate_jwt_kek(cls, v: str) -> str:
        if not v:
            return v  # empty is permitted; lifespan rejects the jwt+empty combination at boot
        try:
            decoded = base64.b64decode(v, validate=True)
        except Exception:
            raise ValueError("JWT_KEK must be valid base64")
        if len(decoded) != 32:
            raise ValueError(
                f"JWT_KEK must decode to exactly 32 bytes; got {len(decoded)}"
            )
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
