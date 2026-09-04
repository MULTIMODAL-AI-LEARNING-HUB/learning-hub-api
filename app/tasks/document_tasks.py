"""Task dispatch helpers for document processing."""

from app.core.celery import celery_app


def dispatch_process_document(document_id: str) -> None:
    celery_app.send_task("process_document_task", args=[document_id])
