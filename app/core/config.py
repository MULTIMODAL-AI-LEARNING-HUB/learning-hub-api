from typing import Any
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Learning Hub API"
    DEBUG: bool = False

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_learning_hub"
    REDIS_URL: str = "redis://localhost:6379/0"
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333

    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin123"
    MINIO_BUCKET_NAME: str = "documents-bucket"
    MINIO_SECURE: bool = False

    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 30
    DB_POOL_RECYCLE: int = 1800
    DB_POOL_PRE_PING: bool = True

    REDIS_CACHE_TTL_DOCS: int = 60
    REDIS_CACHE_TTL_PROFILE: int = 300
    REDIS_CACHE_TTL_QUIZ: int = 3600
    AI_SERVICE_TIMEOUT: int = 60

    RATE_LIMIT_AUTH: str = "10/minute"
    RATE_LIMIT_CHAT: str = "30/minute"
    RATE_LIMIT_UPLOAD: str = "5/minute"
    RATE_LIMIT_ADMIN: str = "60/minute"

    SECRET_KEY: str = "mysecretkey"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    CORS_ORIGINS: Any = ["http://localhost:5173"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                try:
                    import json
                    return json.loads(v)
                except Exception:
                    v = v[1:-1]
            return [i.strip().strip("'\"") for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        raise ValueError(v)

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_url(cls, v: Any) -> str:
        if isinstance(v, str):
            if v.startswith("postgres://"):
                v = v.replace("postgres://", "postgresql://", 1)
            if v.startswith("postgresql://") and not v.startswith("postgresql+asyncpg://"):
                v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    AI_SERVICE_URL: str = "http://localhost:8001"
    INTERNAL_API_KEY: str = "your_internal_api_key"

    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = False
    MAIL_FROM: str = "noreply@learninghub.ai"
    MAIL_FROM_NAME: str = "Learning Hub"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
