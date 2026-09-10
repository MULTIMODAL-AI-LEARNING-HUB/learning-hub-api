"""Study tool endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.cache import RedisCache

# Core/Limiter imports
from app.core.limiter import limiter
from app.dependencies.auth import get_current_user
from app.dependencies.course_auth import verify_course_access
from app.dependencies.db import get_db
from app.models.essay import EssaySubmission
from app.models.flashcard import Flashcard
from app.models.quiz_set import QuizQuestion, QuizSet
from app.models.user import User
from app.repositories.study_repo import StudyRepository
from app.schemas.study import (
    EssayJobResponse,
    EssayResponse,
    EssaySubmitRequest,
    FlashcardGenerateRequest,
    FlashcardHistoryItem,
    FlashcardHistoryListResponse,
    FlashcardItemResponse,
    FlashcardResponse,
    QuizDetailResponse,
    QuizGenerateByCourseRequest,
    QuizGenerateRequest,
    QuizHistoryItem,
    QuizHistoryListResponse,
    QuizJobResponse,
    QuizPersistedQuestion,
    QuizResultResponse,
    QuizSubmitRequest,
)

router = APIRouter()


@router.post("/quiz/generate", response_model=QuizJobResponse, status_code=202)
@limiter.limit(settings.RATE_LIMIT_CHAT)
async def generate_quiz(
    request: Request,
    payload: QuizGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QuizJobResponse:
    """Trigger background quiz generation via Celery."""
    from app.repositories.document_repo import DocumentRepository
    doc = await DocumentRepository(db).get_by_id(payload.document_id)
    if not doc or doc.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied for document"
        )

    from app.tasks.quiz_tasks import dispatch_generate_quiz

    job_id = dispatch_generate_quiz(str(payload.document_id), payload.quiz_type, payload.question_count)
    await RedisCache().set(RedisCache.cache_key_quiz_job(job_id), str(current_user.id), ttl=settings.REDIS_CACHE_TTL_QUIZ)
    import json as _json
    try:
        await RedisCache().set(
            f"cache:quiz_meta:{job_id}",
            _json.dumps({"document_id": str(payload.document_id), "quiz_type": payload.quiz_type}),
            ttl=settings.REDIS_CACHE_TTL_QUIZ * 24 * 7,
        )
    except Exception:
        pass
    return QuizJobResponse(job_id=job_id, status="processing")


@router.post("/quiz/by-course", response_model=QuizJobResponse, status_code=202)
@limiter.limit(settings.RATE_LIMIT_CHAT)
async def generate_quiz_by_course(
    request: Request,
    payload: QuizGenerateByCourseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QuizJobResponse:
    """Trigger quiz generation from course materials via AI service."""
    from app.repositories.course_repo import CourseRepository

    course = await CourseRepository(db).get_by_id(payload.course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    if not await verify_course_access(course, current_user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be enrolled to generate quiz from this course"
        )

    from app.tasks.quiz_tasks import dispatch_generate_quiz_by_course
    lesson_ids = [str(m) for m in (payload.lesson_ids or [])]
    job_id = dispatch_generate_quiz_by_course(
        str(payload.course_id),
        lesson_ids,
        payload.quiz_type,
        payload.question_count
    )
    await RedisCache().set(RedisCache.cache_key_quiz_job(job_id), str(current_user.id), ttl=settings.REDIS_CACHE_TTL_QUIZ)
    return QuizJobResponse(job_id=job_id, status="processing")


@router.get("/quiz/job/{job_id}")
async def get_quiz_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve status or results of a background quiz generation job.

    When the job is ready, the questions are persisted to quiz_sets /
    quiz_questions (once per job_id) so history survives tab switches and
    the Redis TTL expiry.
    """
    owner = await RedisCache().get(RedisCache.cache_key_quiz_job(job_id))
    if owner is None or str(owner) != str(current_user.id):
        repo = StudyRepository(db)
        existing = await repo.get_quiz_set_by_job(job_id)
        if existing and existing.user_id == current_user.id:
            full = await repo.get_quiz_set(existing.id)
            questions = sorted(full.questions, key=lambda q: q.position) if full else []
            return {
                "job_id": job_id,
                "status": "ready",
                "quiz_set_id": str(existing.id),
                "questions": [
                    {"id": str(q.id), "question": q.question_text, "options": q.options, "correct_answer": q.correct_answer}
                    for q in questions
                ],
            }
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz job not found")

    from app.tasks.quiz_tasks import get_quiz_job_status
    result = get_quiz_job_status(job_id)
    if result.get("status") == "ready":
        from uuid import UUID as _UUID
        repo = StudyRepository(db)
        existing = await repo.get_quiz_set_by_job(job_id)
        if existing is None:
            questions = result.get("questions", []) or []
            document_id = None
            quiz_type = "quick"
            try:
                import json as _j
                meta_raw = await RedisCache().get(f"cache:quiz_meta:{job_id}")
                if meta_raw:
                    meta = _j.loads(meta_raw)
                    if meta.get("document_id"):
                        document_id = _UUID(str(meta["document_id"]))
                    quiz_type = meta.get("quiz_type", "quick")
            except Exception:
                pass
            quiz_set = QuizSet(
                user_id=current_user.id,
                document_id=document_id,
                job_id=job_id,
                quiz_type=quiz_type,
                question_count=len(questions),
            )
            quiz_set = await repo.create_quiz_set(quiz_set)
            items: list[QuizQuestion] = []
            for pos, q in enumerate(questions):
                try:
                    qid = q.get("id")
                    _UUID(str(qid))
                except Exception:
                    from uuid import uuid4 as _uuid4
                    qid = _uuid4()
                items.append(
                    QuizQuestion(
                        id=qid if isinstance(qid, _UUID) else qid,
                        quiz_set_id=quiz_set.id,
                        question_text=str(q.get("question", ""))[:4000],
                        options=list(q.get("options", []) or [])[:8],
                        correct_answer=str(q.get("correct_answer", ""))[:10],
                        position=pos,
                    )
                )
            if items:
                await repo.add_quiz_questions(items)
            try:
                await RedisCache().set(
                    RedisCache.cache_key_quiz_job(job_id), str(current_user.id), ttl=settings.REDIS_CACHE_TTL_QUIZ * 24 * 7
                )
            except Exception:
                pass
            result["quiz_set_id"] = str(quiz_set.id)
        else:
            result["quiz_set_id"] = str(existing.id)
    return result


@router.get("/quiz/history", response_model=QuizHistoryListResponse)
async def list_quiz_history(
    document_id: UUID | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QuizHistoryListResponse:
    """List persisted quiz sets for the current user (newest first)."""
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    repo = StudyRepository(db)
    rows, total = await repo.list_quiz_sets(current_user.id, document_id, (page - 1) * page_size, page_size)
    return QuizHistoryListResponse(
        items=[
            QuizHistoryItem(
                id=r.id, document_id=r.document_id, quiz_type=r.quiz_type,
                question_count=r.question_count, created_at=r.created_at,
            )
            for r in rows
        ],
        total=total,
    )


@router.get("/quiz/sets/{quiz_set_id}", response_model=QuizDetailResponse)
async def get_quiz_set_detail(
    quiz_set_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QuizDetailResponse:
    """Get a persisted quiz set with questions (survives tab switches)."""
    repo = StudyRepository(db)
    quiz_set = await repo.get_quiz_set(quiz_set_id)
    if not quiz_set or quiz_set.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    questions = sorted(quiz_set.questions, key=lambda q: q.position)
    return QuizDetailResponse(
        id=quiz_set.id,
        document_id=quiz_set.document_id,
        quiz_type=quiz_set.quiz_type,
        questions=[
            QuizPersistedQuestion(id=q.id, question=q.question_text, options=q.options, correct_answer=q.correct_answer)
            for q in questions
        ],
        created_at=quiz_set.created_at,
    )


@router.delete("/quiz/sets/{quiz_set_id}", status_code=204)
async def delete_quiz_set(
    quiz_set_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a persisted quiz set owned by the current user."""
    repo = StudyRepository(db)
    ok = await repo.delete_quiz_set(quiz_set_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")


@router.post("/quiz/{quiz_id}/submit", response_model=QuizResultResponse)
async def submit_quiz(
    quiz_id: UUID,
    payload: QuizSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QuizResultResponse:
    """Submit answers and grade against the persisted set (DB first, Celery fallback).

    Grading from the DB keeps review working after tab switches / TTL expiry.
    """
    repo = StudyRepository(db)
    quiz_set = await repo.get_quiz_set(quiz_id)
    if quiz_set and quiz_set.user_id == current_user.id:
        qmap = {str(q.id): str(q.correct_answer) for q in quiz_set.questions}
        results = [
            {
                "question_id": str(a.question_id),
                "correct": str(a.answer) == qmap.get(str(a.question_id), ""),
                "correct_answer": qmap.get(str(a.question_id), ""),
                "your_answer": str(a.answer),
            }
            for a in payload.answers
        ]
    else:
        owner = await RedisCache().get(RedisCache.cache_key_quiz_job(str(quiz_id)))
        if owner is None or str(owner) != str(current_user.id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
        from app.tasks.quiz_tasks import get_quiz_results
        results = get_quiz_results(str(quiz_id), [a.model_dump() for a in payload.answers])
    correct = sum(1 for r in results if r["correct"])
    total = len(results)
    return QuizResultResponse(
        score=correct,
        total=total,
        percentage=round(correct / total * 100, 2) if total else 0,
        results=results,
    )


@router.post("/flashcards/generate", response_model=FlashcardResponse, status_code=201)
@limiter.limit(settings.RATE_LIMIT_CHAT)
async def generate_flashcards(
    request: Request,
    payload: FlashcardGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FlashcardResponse:
    """Trigger flashcard generation in the background."""
    from app.repositories.document_repo import DocumentRepository
    doc = await DocumentRepository(db).get_by_id(payload.document_id)
    if not doc or doc.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied for document"
        )

    repo = StudyRepository(db)

    flashcard = Flashcard(
        user_id=current_user.id,
        document_id=payload.document_id,
        set_name=payload.set_name,
    )
    flashcard = await repo.create_flashcard(flashcard)

    from app.tasks.flashcard_tasks import dispatch_generate_flashcards

    dispatch_generate_flashcards(str(flashcard.id), str(payload.document_id), payload.set_name, payload.count)

    from datetime import datetime, timezone
    return FlashcardResponse(
        id=flashcard.id,
        set_name=flashcard.set_name,
        document_id=flashcard.document_id,
        items=[],
        created_at=datetime.now(timezone.utc),
    )


@router.get("/flashcards/sets/{flashcard_id}", response_model=FlashcardResponse)
@router.get("/flashcards/{flashcard_id}", response_model=FlashcardResponse)
async def get_flashcard(
    flashcard_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FlashcardResponse:
    """Get flashcards and eager loaded items."""
    repo = StudyRepository(db)
    flashcard = await repo.get_flashcard(flashcard_id)
    if not flashcard or flashcard.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flashcard set not found")

    items = [
        FlashcardItemResponse(
            id=item.id,
            front=item.front_text,
            back=item.back_text,
            last_reviewed=item.last_reviewed,
        )
        for item in flashcard.items
    ]
    return FlashcardResponse(
        id=flashcard.id,
        set_name=flashcard.set_name,
        document_id=flashcard.document_id,
        items=items,
        created_at=flashcard.created_at,
    )


@router.get("/flashcards", response_model=FlashcardHistoryListResponse)
@router.get("/flashcards/history", response_model=FlashcardHistoryListResponse)
async def list_flashcards_history(
    document_id: UUID | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FlashcardHistoryListResponse:
    """List persisted flashcard sets for the current user."""
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    repo = StudyRepository(db)
    rows, total = await repo.list_flashcards(current_user.id, document_id, (page - 1) * page_size, page_size)
    return FlashcardHistoryListResponse(
        items=[
            FlashcardHistoryItem(
                id=fc.id,
                document_id=fc.document_id,
                set_name=fc.set_name,
                item_count=count or 0,
                created_at=fc.created_at,
            )
            for fc, count in rows
        ],
        total=total,
    )


@router.delete("/flashcards/{flashcard_id}", status_code=204)
async def delete_flashcard(
    flashcard_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a persisted flashcard set owned by the current user."""
    repo = StudyRepository(db)
    ok = await repo.delete_flashcard(flashcard_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flashcard set not found")


@router.post("/essay/submit", response_model=EssayJobResponse, status_code=202)
@limiter.limit(settings.RATE_LIMIT_CHAT)
async def submit_essay(
    request: Request,
    payload: EssaySubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EssayJobResponse:
    """Submit essay for async AI grading. Poll /essay/job/{job_id} for results."""
    from app.repositories.document_repo import DocumentRepository
    doc = await DocumentRepository(db).get_by_id(payload.document_id)
    if not doc or doc.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied for document"
        )

    repo = StudyRepository(db)

    submission = EssaySubmission(
        user_id=current_user.id,
        document_id=payload.document_id,
        submission_text=payload.essay_text,
    )
    submission = await repo.create_essay_submission(submission)

    from app.tasks.essay_tasks import dispatch_grade_essay

    job_id = dispatch_grade_essay(
        str(payload.document_id),
        str(submission.id),
        payload.essay_text,
    )
    await RedisCache().set(
        f"cache:essay_job:{job_id}",
        str(current_user.id),
        ttl=3600,
    )
    return EssayJobResponse(job_id=job_id, status="processing")


@router.get("/essay/job/{job_id}")
async def get_essay_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Poll essay grading job status and retrieve results when ready."""
    from datetime import datetime, timezone

    owner = await RedisCache().get(f"cache:essay_job:{job_id}")
    if owner is None or str(owner) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Essay job not found")

    from app.tasks.essay_tasks import get_essay_job_status

    job = get_essay_job_status(job_id)

    if job["status"] == "processing":
        return EssayJobResponse(job_id=job_id, status="processing")

    if job["status"] == "failed":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Essay grading failed",
        )

    return EssayResponse(
        submission_id=job_id,
        score=job.get("score", 0),
        feedback=job.get("feedback", ""),
        comparisons=job.get("comparisons", []),
        graded_at=datetime.now(timezone.utc),
    )
