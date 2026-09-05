from typing import Any

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REQUIRED_CORS_ORIGINS = {
    "https://learninghubs.tech",
    "https://www.learninghubs.tech",
}


class Settings(BaseSettings):
    APP_NAME: str = "Learning Hub API"
    DEBUG: bool = False

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_learning_hub"
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_URL: str | None = None
    QDRANT_API_KEY: str | None = None

    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin123"
    MINIO_BUCKET_NAME: str = "documents-bucket"
    MINIO_SECURE: bool = False

    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE: int = 1800
    DB_POOL_PRE_PING: bool = True
    DB_SSL_MODE: str = "require"

    REDIS_CACHE_TTL_DOCS: int = 60
    REDIS_CACHE_TTL_PROFILE: int = 300
    REDIS_CACHE_TTL_QUIZ: int = 3600
    REDIS_CACHE_TTL_COURSES: int = 120
    REDIS_CACHE_TTL_CATEGORIES: int = 600
    REDIS_CACHE_TTL_ENROLLMENTS: int = 60
    REDIS_CACHE_TTL_ANNOUNCEMENTS: int = 120
    REDIS_CACHE_TTL_LESSONS: int = 120
    RATE_LIMIT_AUTH: str = "60/minute"
    RATE_LIMIT_LOGIN: str = "10/minute"
    RATE_LIMIT_REGISTER: str = "10/minute"
    RATE_LIMIT_CHAT: str = "30/minute"
    RATE_LIMIT_UPLOAD: str = "5/minute"
    RATE_LIMIT_ADMIN: str = "60/minute"

    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # OAuth Settings
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    FACEBOOK_APP_ID: str = ""
    FACEBOOK_APP_SECRET: str = ""


    CORS_ORIGINS: Any = ["http://localhost:5173", *sorted(REQUIRED_CORS_ORIGINS)]
    FRONTEND_URL: str = "https://learninghubs.tech"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> list[str]:
        origins: list[str]
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                try:
                    import json
                    origins = json.loads(v)
                except Exception:
                    v = v[1:-1]
                    origins = [i.strip().strip("'\"") for i in v.split(",") if i.strip()]
            else:
                origins = [i.strip().strip("'\"") for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            origins = v
        else:
            raise ValueError(v)

        normalized = {str(origin).rstrip("/") for origin in origins if origin}
        return sorted(normalized | REQUIRED_CORS_ORIGINS)

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_url(cls, v: Any) -> str:
        if isinstance(v, str):
            if v.startswith("postgres://"):
                v = v.replace("postgres://", "postgresql://", 1)
            if v.startswith("postgresql://") and not v.startswith("postgresql+asyncpg://"):
                v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
            
            # Strip 'pgbouncer' query parameter as asyncpg doesn't support it
            from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
            try:
                parsed = urlparse(v)
                if parsed.query:
                    query_params = parse_qsl(parsed.query)
                    filtered_params = [(k, val) for k, val in query_params if k.lower() != 'pgbouncer']
                    v = urlunparse(parsed._replace(query=urlencode(filtered_params)))
            except Exception:
                pass
        return v

    AI_SERVICE_URL: str = "http://localhost:8001"
    AI_SERVICE_TIMEOUT: float = 30.0
    INTERNAL_API_KEY: str = ""

    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = False
    MAIL_FROM: str = "noreply@learninghub.ai"
    MAIL_FROM_NAME: str = "Learning Hub"

    # Payment Gateway Configuration
    VNPAY_URL: str = "https://sandbox.vnpay.vn/payv2/vpcpay.html"
    VNPAY_MERCHANT_ID: str = ""
    VNPAY_HASH_SECRET: str = ""
    VNPAY_RETURN_URL: str = "http://localhost:5173/payment/return"

    MOMO_URL: str = "https://test-payment.momo.vn/v2/gateway/api/create"
    MOMO_PARTNER_CODE: str = ""
    MOMO_ACCESS_KEY: str = ""
    MOMO_SECRET_KEY: str = ""
    MOMO_RETURN_URL: str = "http://localhost:5173/payment/return"

    @model_validator(mode="after")
    def validate_secrets(self) -> "Settings":
        import os
        import sys
        # Bypass validation during migrations (alembic) or test execution
        is_migration_or_test = (
            "alembic" in sys.modules
            or any("alembic" in arg for arg in sys.argv)
            or os.environ.get("MIGRATION_MODE") == "True"
            or "pytest" in sys.modules
        )
        if is_migration_or_test:
            return self

        # These checks ALWAYS run regardless of DEBUG
        WEAK_SECRET_KEYS = {"", "mysecretkey", "your_secret_key_for_jwt", "changeme", "secret"}
        WEAK_INTERNAL_KEYS = {"", "your_internal_api_key", "your_internal_key", "changeme", "secret"}

        if not self.SECRET_KEY or self.SECRET_KEY in WEAK_SECRET_KEYS or len(self.SECRET_KEY) < 32:
            raise ValueError(
                "SECRET_KEY must be a secure, non-default string (min 32 chars). "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if not self.INTERNAL_API_KEY or self.INTERNAL_API_KEY in WEAK_INTERNAL_KEYS or len(self.INTERNAL_API_KEY) < 16:
            raise ValueError(
                "INTERNAL_API_KEY must be a secure, non-default string (min 16 chars). "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(16))\""
            )

        # Additional production-only checks
        if not self.DEBUG:
            if not self.MINIO_SECRET_KEY or self.MINIO_SECRET_KEY == "minioadmin123":
                raise ValueError("MINIO_SECRET_KEY must not be the default value in production")
        return self

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
