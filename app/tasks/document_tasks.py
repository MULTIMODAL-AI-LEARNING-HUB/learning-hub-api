"""Task dispatch helpers for document processing."""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "learning_hub_api",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.REDIS_URL,
)


def dispatch_process_document(document_id: str) -> None:
    celery_app.send_task("process_document_task", args=[document_id])
