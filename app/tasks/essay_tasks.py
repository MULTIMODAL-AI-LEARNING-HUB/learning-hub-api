"""Task dispatch helpers for essay grading."""

from celery.result import AsyncResult

from app.core.celery import celery_app


def dispatch_grade_essay(document_id: str, submission_id: str, essay_text: str) -> str:
    """Dispatch an essay grading task to the Celery worker."""
    task = celery_app.send_task(
        "grade_essay_task",
        args=[document_id, submission_id, essay_text],
    )
    return task.id


def get_essay_job_status(job_id: str) -> dict:
    """Retrieve the status and results of an essay grading job."""
    res = AsyncResult(job_id, app=celery_app)
    if res.state == "SUCCESS":
        result_data = res.result or {}
        grade = result_data.get("grade", {})
        return {
            "job_id": job_id,
            "status": "ready",
            "score": grade.get("score", 0),
            "feedback": grade.get("feedback", ""),
            "comparisons": grade.get("comparisons", []),
        }
    elif res.state == "FAILURE":
        return {
            "job_id": job_id,
            "status": "failed",
            "error": "Essay grading failed",
        }
    else:
        return {
            "job_id": job_id,
            "status": "processing",
        }
