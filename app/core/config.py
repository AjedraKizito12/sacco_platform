from functools import lru_cache

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
    platform_auth_mode: str = "stub"  # change to 'jwt' when IAM ships
    platform_bootstrap_email: str = ""
    platform_bootstrap_full_name: str = "Platform Admin"


@lru_cache
def get_settings() -> Settings:
    return Settings()
