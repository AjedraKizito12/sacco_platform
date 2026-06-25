import base64
from functools import lru_cache

from pydantic import field_validator, model_validator
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
    platform_auth_mode: str = "jwt"  # "stub" | "jwt" — stub requires explicit opt-in
    platform_bootstrap_email: str = ""
    platform_bootstrap_full_name: str = "Platform Admin"

    # Tenant auth
    tenant_auth_mode: str = "jwt"  # "stub" | "jwt" — stub requires explicit opt-in

    # Member auth (Phase 4a — member self-service portal)
    member_auth_mode: str = "jwt"  # "stub" | "jwt" — stub requires explicit opt-in

    # JWT signing key infrastructure
    jwt_kek: str = ""  # base64-encoded 32-byte key-encryption-key; required when auth_mode=jwt
    jwt_key_rotation_days: int = 90
    jwt_access_ttl_seconds: int = 900             # 15 min
    jwt_refresh_ttl_platform_seconds: int = 3600  # 1 h
    jwt_refresh_ttl_tenant_seconds: int = 28800   # 8 h
    jwt_refresh_ttl_member_seconds: int = 28800   # 8 h

    # Impersonation
    impersonation_max_minutes: int = 30  # max duration of a single impersonation session
    impersonation_default_required_approvals: int = 1  # checker quorum for start_impersonation

    # Password policy
    auth_password_min_length: int = 12  # characters; no complexity rules in v1

    # Lockout policy
    auth_lockout_threshold: int = 5          # failed attempts before lockout
    auth_lockout_window_minutes: int = 15    # sliding window for counting attempts
    auth_lockout_duration_minutes: int = 30  # how long the account stays locked

    @field_validator("jwt_kek")
    @classmethod
    def validate_jwt_kek(cls, v: str) -> str:
        if not v:
            return v  # empty is permitted at field level; model validator enforces presence
        try:
            decoded = base64.b64decode(v, validate=True)
        except Exception:
            raise ValueError("JWT_KEK must be valid base64") from None
        if len(decoded) != 32:
            raise ValueError(
                f"JWT_KEK must decode to exactly 32 bytes; got {len(decoded)}"
            )
        return v

    @model_validator(mode="after")
    def validate_kek_required_for_jwt_mode(self) -> "Settings":
        """Require a non-empty JWT_KEK whenever either auth mode is 'jwt'.

        The field-level validator (validate_jwt_kek) already enforces that if
        jwt_kek is non-empty it must be valid base64 of exactly 32 bytes. This
        model-level validator enforces that it is non-empty when needed.

        Generate a key:
            python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
        """
        if (
            self.platform_auth_mode == "jwt"
            or self.tenant_auth_mode == "jwt"
            or self.member_auth_mode == "jwt"
        ) and not self.jwt_kek:
            raise ValueError(
                "JWT_KEK must be set when PLATFORM_AUTH_MODE, TENANT_AUTH_MODE, "
                "or MEMBER_AUTH_MODE is 'jwt'. "
                "Generate with: "
                "python -c \"import os,base64; print(base64.b64encode(os.urandom(32)).decode())\""
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
