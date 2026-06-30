from fastapi import APIRouter, Depends, HTTPException, status
from uuid import UUID
from typing import List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import Lesson, Quiz, Question, Answer, Course, Enrollment, QuizAttempt
from app.schemas.course_content import (
    QuizCreate, QuizUpdate, QuizResponse, QuizWithQuestions,
    QuestionCreate, QuestionUpdate, QuestionResponse, QuestionWithAnswers,
    AnswerCreate, AnswerUpdate, AnswerResponse,
    QuizAttemptSubmit, QuizAttemptResponse, QuizAttemptResult,
    ReorderQuestions
)
from app.dependencies.auth import get_current_user, require_lecturer, get_current_active_user
from app.models.user import User

router = APIRouter(prefix="/lessons/{lesson_id}/quiz", tags=["Quizzes"])


async def get_lesson_with_course(db: AsyncSession, lesson_id: UUID) -> tuple[Lesson, Course]:
    result = await db.execute(
        select(Lesson).where(Lesson.id == lesson_id).options(selectinload(Lesson.section).selectinload(Lesson.course))
    )
    lesson = result.scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson, lesson.section.course


async def verify_course_ownership(course: Course, current_user: User) -> None:
    if course.lecturer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")


# ============ QUIZ ROUTES ============

@router.get("", response_model=QuizWithQuestions)
async def get_quiz(
    lesson_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)

    result = await db.execute(
        select(Quiz)
        .where(Quiz.lesson_id == lesson_id)
        .options(selectinload(Quiz.questions).selectinload(Quiz.answers))
    )
    quiz = result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    return quiz


@router.post("", response_model=QuizResponse, status_code=status.HTTP_201_CREATED)
async def create_quiz(
    lesson_id: UUID,
    quiz_data: QuizCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)
    await verify_course_ownership(course, current_user)

    existing = await db.execute(select(Quiz).where(Quiz.lesson_id == lesson_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Quiz already exists for this lesson")

    quiz = Quiz(
        lesson_id=lesson_id,
        title=quiz_data.title,
        description=quiz_data.description,
        passing_score=quiz_data.passing_score,
        duration_mins=quiz_data.duration_mins,
        max_attempts=quiz_data.max_attempts
    )
    db.add(quiz)
    await db.commit()
    await db.refresh(quiz)
    return quiz


@router.put("", response_model=QuizResponse)
async def update_quiz(
    lesson_id: UUID,
    quiz_data: QuizUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)
    await verify_course_ownership(course, current_user)

    result = await db.execute(select(Quiz).where(Quiz.lesson_id == lesson_id))
    quiz = result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    for key, value in quiz_data.model_dump(exclude_unset=True).items():
        setattr(quiz, key, value)

    await db.commit()
    await db.refresh(quiz)
    return quiz


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quiz(
    lesson_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)
    await verify_course_ownership(course, current_user)

    result = await db.execute(select(Quiz).where(Quiz.lesson_id == lesson_id))
    quiz = result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    await db.delete(quiz)
    await db.commit()


# ============ QUESTION ROUTES ============

@router.post("/questions", response_model=QuestionResponse, status_code=status.HTTP_201_CREATED)
async def create_question(
    lesson_id: UUID,
    question_data: QuestionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)
    await verify_course_ownership(course, current_user)

    result = await db.execute(select(Quiz).where(Quiz.lesson_id == lesson_id))
    quiz = result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(status_code=400, detail="Quiz not found for this lesson")

    question = Question(
        quiz_id=quiz.id,
        question_text=question_data.question_text,
        type=question_data.type,
        points=question_data.points,
        explanation=question_data.explanation,
        order_index=question_data.order_index
    )
    db.add(question)
    await db.commit()
    await db.refresh(question)
    return question


@router.put("/questions/{question_id}", response_model=QuestionResponse)
async def update_question(
    lesson_id: UUID,
    question_id: UUID,
    question_data: QuestionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)
    await verify_course_ownership(course, current_user)

    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    for key, value in question_data.model_dump(exclude_unset=True).items():
        setattr(question, key, value)

    await db.commit()
    await db.refresh(question)
    return question


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(
    lesson_id: UUID,
    question_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)
    await verify_course_ownership(course, current_user)

    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    await db.delete(question)
    await db.commit()


@router.put("/questions/reorder", response_model=List[QuestionResponse])
async def reorder_questions(
    lesson_id: UUID,
    reorder_data: ReorderQuestions,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)
    await verify_course_ownership(course, current_user)

    for idx, qid in enumerate(reorder_data.question_ids):
        result = await db.execute(select(Question).where(Question.id == qid))
        question = result.scalar_one_or_none()
        if question:
            question.order_index = idx

    await db.commit()
    result = await db.execute(select(Question).where(Question.quiz_id == Lesson.id).order_by(Question.order_index))
    questions = result.scalars().all()
    return questions


# ============ ANSWER ROUTES ============

@router.post("/questions/{question_id}/answers", response_model=AnswerResponse, status_code=status.HTTP_201_CREATED)
async def create_answer(
    lesson_id: UUID,
    question_id: UUID,
    answer_data: AnswerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)
    await verify_course_ownership(course, current_user)

    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    answer = Answer(
        question_id=question_id,
        answer_text=answer_data.answer_text,
        is_correct=answer_data.is_correct,
        order_index=answer_data.order_index
    )
    db.add(answer)
    await db.commit()
    await db.refresh(answer)
    return answer


@router.put("/answers/{answer_id}", response_model=AnswerResponse)
async def update_answer(
    lesson_id: UUID,
    answer_id: UUID,
    answer_data: AnswerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)
    await verify_course_ownership(course, current_user)

    result = await db.execute(select(Answer).where(Answer.id == answer_id))
    answer = result.scalar_one_or_none()
    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")

    for key, value in answer_data.model_dump(exclude_unset=True).items():
        setattr(answer, key, value)

    await db.commit()
    await db.refresh(answer)
    return answer


@router.delete("/answers/{answer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_answer(
    lesson_id: UUID,
    answer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)
    await verify_course_ownership(course, current_user)

    result = await db.execute(select(Answer).where(Answer.id == answer_id))
    answer = result.scalar_one_or_none()
    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")

    await db.delete(answer)
    await db.commit()


@router.post("/answers/{answer_id}/correct-toggle", response_model=AnswerResponse)
async def toggle_correct_answer(
    lesson_id: UUID,
    answer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)
    await verify_course_ownership(course, current_user)

    result = await db.execute(select(Answer).where(Answer.id == answer_id))
    answer = result.scalar_one_or_none()
    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")

    answer.is_correct = not answer.is_correct
    await db.commit()
    await db.refresh(answer)
    return answer


# ============ QUIZ ATTEMPT ROUTES (STUDENT) ============

@router.post("/attempt", response_model=QuizAttemptResponse, status_code=status.HTTP_201_CREATED)
async def start_quiz_attempt(
    lesson_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)

    enrollment_result = await db.execute(
        select(Enrollment).where(
            Enrollment.student_id == current_user.id,
            Enrollment.course_id == course.id,
            Enrollment.status == "active"
        )
    )
    enrollment = enrollment_result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=403, detail="Not enrolled in this course")

    result = await db.execute(select(Quiz).where(Quiz.lesson_id == lesson_id))
    quiz = result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    attempt_count = await db.execute(
        select(QuizAttempt).where(
            QuizAttempt.enrollment_id == enrollment.id,
            QuizAttempt.quiz_id == quiz.id
        )
    )
    attempts = attempt_count.scalars().all()
    if len(attempts) >= quiz.max_attempts:
        raise HTTPException(status_code=400, detail="Maximum attempts reached")

    attempt = QuizAttempt(
        enrollment_id=enrollment.id,
        quiz_id=quiz.id,
        attempt_number=len(attempts) + 1
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)
    return attempt


@router.put("/attempt/{attempt_id}/submit", response_model=QuizAttemptResult)
async def submit_quiz_attempt(
    lesson_id: UUID,
    attempt_id: UUID,
    submission: QuizAttemptSubmit,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)

    result = await db.execute(
        select(QuizAttempt).where(QuizAttempt.id == attempt_id)
    )
    attempt = result.scalar_one_or_none()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")

    quiz_result = await db.execute(select(Quiz).where(Quiz.lesson_id == lesson_id))
    quiz = quiz_result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    correct_count = 0
    total_points = 0
    earned_points = 0

    questions_result = await db.execute(
        select(Question).where(Question.quiz_id == quiz.id)
    )
    questions = questions_result.scalars().all()

    for question in questions:
        total_points += question.points
        question_answers_result = await db.execute(
            select(Answer).where(Answer.question_id == question.id)
        )
        question_answers = question_answers_result.scalars().all()
        correct_answer_ids = [a.id for a in question_answers if a.is_correct]

        submission_for_q = next((s for s in submission.answers if s.get("question_id") == str(question.id)), None)
        if submission_for_q:
            selected = submission_for_q.get("selected_answers", [])
            if set(selected) == set(str(a) for a in correct_answer_ids):
                correct_count += 1
                earned_points += question.points

    score = (earned_points / total_points * 100) if total_points > 0 else 0
    passed = score >= quiz.passing_score

    attempt.score = score
    attempt.max_score = 100
    attempt.passed = passed
    attempt.completed_at = datetime.now()

    await db.commit()
    await db.refresh(attempt)
    return attempt


@router.get("/my-attempts", response_model=List[QuizAttemptResponse])
async def get_my_attempts(
    lesson_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)

    enrollment_result = await db.execute(
        select(Enrollment).where(
            Enrollment.student_id == current_user.id,
            Enrollment.course_id == course.id
        )
    )
    enrollment = enrollment_result.scalar_one_or_none()
    if not enrollment:
        return []

    quiz_result = await db.execute(select(Quiz).where(Quiz.lesson_id == lesson_id))
    quiz = quiz_result.scalar_one_or_none()
    if not quiz:
        return []

    attempts_result = await db.execute(
        select(QuizAttempt)
        .where(QuizAttempt.enrollment_id == enrollment.id, QuizAttempt.quiz_id == quiz.id)
        .order_by(QuizAttempt.started_at.desc())
    )
    attempts = attempts_result.scalars().all()
    return attempts