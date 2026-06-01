"""Study tool endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.essay import EssaySubmission
from app.models.flashcard import Flashcard
from app.models.user import User
from app.repositories.study_repo import StudyRepository
from app.schemas.study import (
    EssayResponse,
    EssaySubmitRequest,
    FlashcardGenerateRequest,
    FlashcardResponse,
    FlashcardItemResponse,
    QuizGenerateRequest,
    QuizJobResponse,
    QuizSubmitRequest,
    QuizResultResponse,
)

router = APIRouter()


@router.post("/quiz/generate", response_model=QuizJobResponse, status_code=202)
async def generate_quiz(
    payload: QuizGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QuizJobResponse:
    from app.tasks.quiz_tasks import dispatch_generate_quiz

    job_id = dispatch_generate_quiz(str(payload.document_id), payload.quiz_type, payload.question_count)
    return QuizJobResponse(job_id=job_id, status="processing")


@router.post("/quiz/{quiz_id}/submit", response_model=QuizResultResponse)
async def submit_quiz(
    quiz_id: UUID,
    payload: QuizSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QuizResultResponse:
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
async def generate_flashcards(
    payload: FlashcardGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FlashcardResponse:
    repo = StudyRepository(db)

    flashcard = Flashcard(
        user_id=current_user.id,
        document_id=payload.document_id,
        set_name=payload.set_name,
    )
    flashcard = await repo.create_flashcard(flashcard)

    from app.tasks.flashcard_tasks import dispatch_generate_flashcards

    await dispatch_generate_flashcards(str(flashcard.id), str(payload.document_id), payload.set_name, payload.count)

    return FlashcardResponse(
        id=flashcard.id,
        set_name=flashcard.set_name,
        document_id=flashcard.document_id,
        items=[],
        created_at=flashcard.created_at,
    )


@router.get("/flashcards/{flashcard_id}", response_model=FlashcardResponse)
async def get_flashcard(
    flashcard_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FlashcardResponse:
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


@router.post("/essay/submit", response_model=EssayResponse)
async def submit_essay(
    payload: EssaySubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EssayResponse:
    repo = StudyRepository(db)

    submission = EssaySubmission(
        user_id=current_user.id,
        document_id=payload.document_id,
        submission_text=payload.essay_text,
    )
    submission = await repo.create_essay_submission(submission)

    import httpx
    from app.core.config import settings

    try:
        response = httpx.post(
            f"{settings.AI_SERVICE_URL}/study/essay/grade",
            json={
                "document_id": str(payload.document_id),
                "essay_text": payload.essay_text,
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        data = {"score": 0, "feedback": "AI service unavailable", "comparisons": []}

    from datetime import datetime, timezone

    return EssayResponse(
        submission_id=submission.id,
        score=data.get("score", 0),
        feedback=data.get("feedback", ""),
        comparisons=data.get("comparisons", []),
        graded_at=datetime.now(timezone.utc),
    )
