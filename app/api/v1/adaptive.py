"""Adaptive Learning and Weak-point Remediation endpoints."""

import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.clients.ai_client import AiClient
from app.dependencies.auth import get_current_user
from app.dependencies.course_auth import get_lesson_with_course, verify_lesson_access
from app.dependencies.db import get_db
from app.models.course import Course
from app.models.course_content import Lesson, Quiz, QuizAttempt
from app.models.enrollment import Enrollment
from app.models.user import User
from app.schemas.adaptive import (
    MissedQuestionItem,
    RemedialQuestionResponse,
    RemedialQuizGenerateRequest,
    RemedialQuizResponse,
    WeaknessAreaItem,
    WeaknessSummaryResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/my-weaknesses", response_model=WeaknessSummaryResponse)
async def get_my_weaknesses(
    limit: int = Query(default=5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WeaknessSummaryResponse:
    """Analyze student quiz attempts to diagnose knowledge gaps and weak areas."""
    # Fetch quiz attempts for the user with enrollment and quiz details
    query = (
        select(QuizAttempt, Quiz, Lesson, Course)
        .join(Enrollment, Enrollment.id == QuizAttempt.enrollment_id)
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .join(Lesson, Lesson.id == Quiz.lesson_id)
        .join(Course, Course.id == Lesson.course_id)
        .where(
            Enrollment.student_id == current_user.id,
            QuizAttempt.completed_at.isnot(None),
        )
        .order_by(desc(QuizAttempt.completed_at))
    )

    result = await db.execute(query)
    rows = result.all()

    # Group attempts by lesson_id to find recent weak performance
    lessons_map: dict[UUID, dict] = {}

    for attempt, quiz, lesson, course in rows:
        lid = lesson.id
        if lid not in lessons_map:
            lessons_map[lid] = {
                "lesson_id": lid,
                "lesson_title": lesson.title,
                "course_id": course.id,
                "course_title": course.title,
                "total_questions": 0,
                "missed_count": 0,
                "last_attempt_at": attempt.completed_at,
                "missed_questions": [],
            }

        details = attempt.answers_detail or []
        for q in details:
            lessons_map[lid]["total_questions"] += 1
            if not q.get("is_correct", False):
                lessons_map[lid]["missed_count"] += 1
                # Avoid duplicate question texts in list
                existing_qids = {mq.question_id for mq in lessons_map[lid]["missed_questions"]}
                qid = str(q.get("question_id", ""))
                if qid not in existing_qids:
                    lessons_map[lid]["missed_questions"].append(
                        MissedQuestionItem(
                            question_id=qid,
                            question_text=q.get("question_text") or "Câu hỏi",
                            selected_answers=q.get("selected_answers") or [],
                            correct_answers=q.get("correct_answers") or [],
                            explanation=q.get("explanation"),
                            is_correct=False,
                        )
                    )

    # Filter to areas that have at least 1 missed question
    weak_areas: list[WeaknessAreaItem] = []
    for data in lessons_map.values():
        total = data["total_questions"]
        missed = data["missed_count"]
        if missed > 0:
            accuracy = round(((total - missed) / total) * 100, 1) if total > 0 else 0.0
            weak_areas.append(
                WeaknessAreaItem(
                    lesson_id=data["lesson_id"],
                    lesson_title=data["lesson_title"],
                    course_id=data["course_id"],
                    course_title=data["course_title"],
                    total_questions=total,
                    missed_count=missed,
                    accuracy_percent=accuracy,
                    last_attempt_at=data["last_attempt_at"],
                    missed_questions=data["missed_questions"][:5],
                )
            )

    # Sort primarily by lowest accuracy, secondarily by highest missed count
    weak_areas.sort(key=lambda w: (w.accuracy_percent, -w.missed_count))

    return WeaknessSummaryResponse(
        weaknesses=weak_areas[:limit],
        total_weak_areas=len(weak_areas),
    )


@router.post("/lessons/{lesson_id}/remedial-quiz", response_model=RemedialQuizResponse)
async def generate_remedial_quiz_for_lesson(
    lesson_id: UUID,
    payload: RemedialQuizGenerateRequest = RemedialQuizGenerateRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RemedialQuizResponse:
    """Generate a targeted 3-5 question micro-quiz targeting student's missed questions in a lesson."""
    lesson, course = await get_lesson_with_course(db, lesson_id)
    await verify_lesson_access(lesson, course, current_user, db)

    # Get the latest completed attempt for this lesson
    query = (
        select(QuizAttempt)
        .join(Enrollment, Enrollment.id == QuizAttempt.enrollment_id)
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .where(
            Enrollment.student_id == current_user.id,
            Quiz.lesson_id == lesson_id,
            QuizAttempt.completed_at.isnot(None),
        )
        .order_by(desc(QuizAttempt.completed_at))
        .limit(1)
    )
    result = await db.execute(query)
    latest_attempt = result.scalar_one_or_none()

    missed_questions = []
    if latest_attempt and latest_attempt.answers_detail:
        missed_questions = [
            q for q in latest_attempt.answers_detail if not q.get("is_correct", False)
        ]

    # If no recorded missed questions yet, fallback to any incorrect answer across attempts or empty
    lesson_content = getattr(lesson, "content", "") or ""

    ai_client = AiClient()
    try:
        ai_res = await ai_client.generate_remedial_quiz(
            missed_questions=missed_questions,
            lesson_id=str(lesson_id),
            course_id=str(course.id),
            lesson_title=lesson.title,
            lesson_content=lesson_content,
            question_count=payload.question_count,
        )
        questions_raw = ai_res.get("questions") or []
    except Exception as exc:
        logger.error("Failed to generate remedial quiz via AI: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Không thể tạo bài kiểm tra củng cố vào lúc này. Vui lòng thử lại sau.",
        )

    questions = [
        RemedialQuestionResponse(
            id=str(q.get("id") or i),
            question=q.get("question") or "",
            options=q.get("options") or [],
            correct_answer=q.get("correct_answer") or "A",
            explanation=q.get("explanation"),
        )
        for i, q in enumerate(questions_raw)
    ]

    return RemedialQuizResponse(
        lesson_id=lesson_id,
        lesson_title=lesson.title,
        target_weaknesses_count=len(missed_questions),
        questions=questions,
    )
