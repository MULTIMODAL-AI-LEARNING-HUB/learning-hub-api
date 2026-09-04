"""Centralized Celery application instance for task dispatching."""

import ssl
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "learning_hub_api",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.REDIS_URL,
)

if settings.CELERY_BROKER_URL.startswith("rediss://"):
    celery_app.conf.update(
        broker_use_ssl={"ssl_cert_reqs": ssl.CERT_NONE},
    )

if settings.REDIS_URL.startswith("rediss://"):
    celery_app.conf.update(
        redis_backend_use_ssl={"ssl_cert_reqs": ssl.CERT_NONE},
    )

