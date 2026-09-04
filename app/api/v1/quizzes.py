from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.dependencies.auth import (
    get_current_user,
    require_active_user,
    require_lecturer,
)
from app.dependencies.course_auth import (
    get_lesson_with_course,
    verify_course_ownership,
    verify_lesson_access,
)
from app.models import (
    Answer,
    Enrollment,
    Lesson,
    Question,
    Quiz,
    QuizAttempt,
)
from app.models.user import User
from app.schemas.course_content import (
    AnswerCreate,
    AnswerResponse,
    AnswerStudentResponse,
    AnswerUpdate,
    QuestionCreate,
    QuestionResponse,
    QuestionStudentResponse,
    QuestionUpdate,
    QuizAttemptResponse,
    QuizAttemptResult,
    QuizAttemptSubmit,
    QuizCreate,
    QuizResponse,
    QuizStudentResponse,
    QuizUpdate,
    QuizWithQuestions,
    ReorderQuestions,
)

router = APIRouter(prefix="/lessons/{lesson_id}/quiz", tags=["Quizzes"])


# ============ QUIZ ROUTES ============

@router.get("", response_model=QuizWithQuestions | QuizStudentResponse)
async def get_quiz(
    lesson_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)
    await verify_lesson_access(lesson, course, current_user, db)

    result = await db.execute(
        select(Quiz)
        .where(Quiz.lesson_id == lesson_id)
        .options(selectinload(Quiz.questions).selectinload(Question.answers))
    )
    quiz = result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    is_privileged = current_user.role == "admin" or course.lecturer_id == current_user.id
    if is_privileged:
        return quiz

    # Omit correct answers for students to prevent cheating
    student_questions = []
    for q in quiz.questions:
        student_answers = [
            AnswerStudentResponse(
                id=a.id,
                question_id=a.question_id,
                answer_text=a.answer_text,
                order_index=a.order_index,
                created_at=a.created_at,
            )
            for a in q.answers
        ]
        student_questions.append(
            QuestionStudentResponse(
                id=q.id,
                quiz_id=q.quiz_id,
                question_text=q.question_text,
                type=q.type,
                points=q.points,
                order_index=q.order_index,
                created_at=q.created_at,
                answers=student_answers,
            )
        )

    return QuizStudentResponse(
        id=quiz.id,
        lesson_id=quiz.lesson_id,
        title=quiz.title,
        description=quiz.description,
        passing_score=quiz.passing_score,
        duration_mins=quiz.duration_mins,
        max_attempts=quiz.max_attempts,
        is_active=quiz.is_active,
        question_count=len(student_questions),
        created_at=quiz.created_at,
        updated_at=quiz.updated_at,
        questions=student_questions,
    )


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


@router.post("/generate-ai", response_model=QuizWithQuestions)
async def generate_quiz_ai(
    lesson_id: UUID,
    question_count: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    from app.clients.ai_client import AiClient
    
    lesson, course = await get_lesson_with_course(db, lesson_id)
    await verify_course_ownership(course, current_user)

    # 1. Ask AI to generate questions
    ai_client = AiClient()
    ai_response = await ai_client.generate_quiz_from_lesson(
        lesson_id=str(lesson_id),
        course_id=str(course.id),
        question_count=question_count,
        lesson_content=lesson.content
    )
    
    ai_questions = ai_response.get("questions", [])
    if not ai_questions:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="AI failed to generate quiz questions")

    # 2. Get or create Quiz for the lesson
    result = await db.execute(select(Quiz).where(Quiz.lesson_id == lesson_id))
    quiz = result.scalar_one_or_none()
    
    if not quiz:
        quiz = Quiz(
            lesson_id=lesson_id,
            title=f"AI Quiz: {lesson.title}",
            description="Quiz auto-generated by AI based on lesson materials.",
            passing_score=70,
            max_attempts=3,
            is_active=True
        )
        db.add(quiz)
        await db.flush()

    # 3. Create Questions & Answers
    # Find next order index
    order_result = await db.execute(
        select(func.max(Question.order_index)).where(Question.quiz_id == quiz.id)
    ) if hasattr(db, 'execute') else None
    
    next_order = 0
    if order_result:
        max_order = order_result.scalar()
        if max_order is not None:
            next_order = max_order + 1

    for idx, ai_q in enumerate(ai_questions):
        question = Question(
            quiz_id=quiz.id,
            question_text=ai_q.get("question", ""),
            type="SINGLE_CHOICE",
            points=1,
            order_index=next_order + idx
        )
        db.add(question)
        await db.flush()

        correct_opt = ai_q.get("correct_answer", "")
        options = ai_q.get("options", [])
        
        # Options could be ["A", "B", "C", "D"] or direct text.
        # AI prompt outputs options and correct_answer directly.
        # Let's map options
        for o_idx, opt_text in enumerate(options):
            # If AI returns correct_answer like "A", "B", "C", "D" and option is indeed that choice, or if the correct answer string matches option text.
            is_correct = False
            if opt_text == correct_opt:
                is_correct = True
            elif correct_opt in ["A", "B", "C", "D"] and o_idx < len(["A", "B", "C", "D"]):
                # Handle cases where correct_opt is a letter index and opt_text is the option text.
                letter = ["A", "B", "C", "D"][o_idx]
                if letter == correct_opt:
                    is_correct = True
            
            answer = Answer(
                question_id=question.id,
                answer_text=opt_text,
                is_correct=is_correct,
                order_index=o_idx
            )
            db.add(answer)

    await db.commit()
    
    # Return quiz with all questions loaded
    final_result = await db.execute(
        select(Quiz)
        .where(Quiz.id == quiz.id)
        .options(selectinload(Quiz.questions).selectinload(Question.answers))
    )
    return final_result.scalar_one()


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
    await db.flush()

    for idx, answer_data in enumerate(question_data.answers):
        answer = Answer(
            question_id=question.id,
            answer_text=answer_data.answer_text,
            is_correct=answer_data.is_correct,
            order_index=answer_data.order_index or idx
        )
        db.add(answer)

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
    current_user: User = Depends(require_active_user)
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
    current_user: User = Depends(require_active_user)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)

    result = await db.execute(
        select(QuizAttempt).where(QuizAttempt.id == attempt_id)
    )
    attempt = result.scalar_one_or_none()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")

    # Verify attempt belongs to current user's enrollment
    enrollment_check = await db.execute(
        select(Enrollment).where(
            Enrollment.id == attempt.enrollment_id,
            Enrollment.student_id == current_user.id
        )
    )
    if not enrollment_check.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not authorized to submit this attempt")

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
    current_user: User = Depends(require_active_user)
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