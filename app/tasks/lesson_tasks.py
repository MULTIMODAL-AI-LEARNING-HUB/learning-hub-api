from app.core.celery import celery_app


def dispatch_process_lesson_content(lesson_id: str, course_id: str | None = None) -> str:
    """Dispatch task to process lesson content (HTML/text) into Qdrant vectors."""
    task = celery_app.send_task(
        "process_lesson_content_task",
        args=[lesson_id],
        kwargs={"course_id": course_id} if course_id else {}
    )
    return task.id


def dispatch_process_course_file(
    storage_key: str,
    course_id: str,
    lesson_id: str | None = None,
    material_id: str | None = None,
    source_type: str = "course_material",
    file_name: str | None = None,
) -> str:
    """Dispatch task to process a file from MinIO with course context metadata.

    Args:
        storage_key: MinIO storage key (e.g., "course_materials/{course_id}/{uuid}.pdf")
        course_id: Course UUID
        lesson_id: Optional lesson UUID for attachments
        material_id: Optional material UUID for course materials
        source_type: "course_material" or "lesson_attachment"
        file_name: Original filename for extension detection
    """
    task = celery_app.send_task(
        "process_course_file_task",
        args=[storage_key, course_id],
        kwargs={
            "lesson_id": lesson_id,
            "material_id": material_id,
            "source_type": source_type,
            "file_name": file_name,
        }
    )
    return task.id