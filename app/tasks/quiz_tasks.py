"""Task helpers for quiz generation."""

from fastapi import HTTPException, status
from celery.result import AsyncResult
from app.tasks.document_tasks import celery_app


def dispatch_generate_quiz(document_id: str, quiz_type: str, question_count: int) -> str:
    """Dispatch a quiz generation task to the Celery worker."""
    task = celery_app.send_task(
        "generate_quiz_task",
        args=[document_id, quiz_type, question_count]
    )
    return task.id


def get_quiz_job_status(job_id: str) -> dict:
    """Retrieve the status and results of a quiz generation job."""
    res = AsyncResult(job_id, app=celery_app)
    if res.state == "SUCCESS":
        result_data = res.result
        return {
            "job_id": job_id,
            "status": "ready",
            "questions": result_data.get("questions", [])
        }
    elif res.state == "FAILURE":
        return {
            "job_id": job_id,
            "status": "failed",
            "error": str(res.result)
        }
    else:
        return {
            "job_id": job_id,
            "status": "processing"
        }


def get_quiz_results(quiz_id: str, user_answers: list[dict]) -> list[dict]:
    """Retrieve the quiz from Celery result backend and grade user answers."""
    res = AsyncResult(quiz_id, app=celery_app)
    if not res.ready():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quiz generation is still in progress"
        )
    if res.failed():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Quiz generation failed"
        )
    
    result_data = res.result
    if not result_data or "questions" not in result_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz data not found"
        )
    
    questions = result_data["questions"]
    # Build map of question ID to correct answer
    question_map = {}
    for q in questions:
        q_id = q.get("id")
        q_ans = q.get("correct_answer")
        question_map[q_id] = q_ans
    
    results = []
    for ans in user_answers:
        q_id = str(ans.get("question_id"))
        your_ans = ans.get("answer")
        correct_ans = question_map.get(q_id, "")
        
        results.append({
            "question_id": q_id,
            "correct": your_ans == correct_ans,
            "correct_answer": correct_ans,
            "your_answer": your_ans
        })
        
    return results
