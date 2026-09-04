"""Centralized Celery application instance for task dispatching."""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "learning_hub_api",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.REDIS_URL,
)
