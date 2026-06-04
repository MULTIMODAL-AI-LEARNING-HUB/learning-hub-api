"""Task helpers for flashcard generation."""

from app.tasks.document_tasks import celery_app


async def dispatch_generate_flashcards(flashcard_id: str, document_id: str, set_name: str, count: int) -> str:
    """Dispatch a flashcard generation task to the Celery worker."""
    task = celery_app.send_task(
        "generate_flashcards_task",
        args=[flashcard_id, document_id, set_name, count]
    )
    return task.id
