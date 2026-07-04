from datetime import datetime
from uuid import UUID
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import Lesson, Section, Assignment, AssignmentSubmission, Course, Enrollment
from app.schemas.course_content import (
    AssignmentCreate, AssignmentUpdate, AssignmentResponse,
    SubmissionCreate, SubmissionGrade, SubmissionResponse
)
from app.dependencies.auth import get_current_user, require_lecturer, require_active_user
from app.models.user import User
from app.clients.minio_client import MinioClient

router = APIRouter(prefix="/lessons/{lesson_id}/assignment", tags=["Assignments"])


async def get_lesson_with_course(db: AsyncSession, lesson_id: UUID) -> tuple[Lesson, Course]:
    result = await db.execute(
        select(Lesson).where(Lesson.id == lesson_id).options(selectinload(Lesson.section).selectinload(Section.course))
    )
    lesson = result.scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson, lesson.section.course


async def verify_course_ownership(course: Course, current_user: User) -> None:
    if course.lecturer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")


def _parse_and_presign_attachments(attachments_str: str | None) -> list:
    if not attachments_str:
        return []
    try:
        # Try JSON parsing first
        import json
        items = json.loads(attachments_str)
    except Exception:
        try:
            # Fall back to safe Python literal evaluation (handles single quotes)
            import ast
            items = ast.literal_eval(attachments_str)
        except Exception:
            return []
            
    if not isinstance(items, list):
        return []
        
    try:
        minio_client = MinioClient()
        for item in items:
            if isinstance(item, dict) and "file_url" in item:
                url = item["file_url"]
                if url and url.startswith("s3://"):
                    try:
                        item["file_url"] = minio_client.get_presigned_url(url)
                    except Exception:
                        pass
    except Exception:
        pass
        
    return items


# ============ ASSIGNMENT ROUTES (LECTURER) ============

@router.get("", response_model=AssignmentResponse)
async def get_assignment(
    lesson_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)
    result = await db.execute(select(Assignment).where(Assignment.lesson_id == lesson_id))
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return assignment


@router.post("", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED)
async def create_assignment(
    lesson_id: UUID,
    assignment_data: AssignmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)
    await verify_course_ownership(course, current_user)

    existing = await db.execute(select(Assignment).where(Assignment.lesson_id == lesson_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Assignment already exists for this lesson")

    assignment = Assignment(
        lesson_id=lesson_id,
        title=assignment_data.title,
        description=assignment_data.description,
        instructions=assignment_data.instructions,
        deadline=assignment_data.deadline,
        max_score=assignment_data.max_score,
        allow_resubmit=assignment_data.allow_resubmit,
        max_resubmits=assignment_data.max_resubmits
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)
    return assignment


@router.put("", response_model=AssignmentResponse)
async def update_assignment(
    lesson_id: UUID,
    assignment_data: AssignmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)
    await verify_course_ownership(course, current_user)

    result = await db.execute(select(Assignment).where(Assignment.lesson_id == lesson_id))
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    for key, value in assignment_data.model_dump(exclude_unset=True).items():
        setattr(assignment, key, value)

    await db.commit()
    await db.refresh(assignment)
    return assignment


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assignment(
    lesson_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)
    await verify_course_ownership(course, current_user)

    result = await db.execute(select(Assignment).where(Assignment.lesson_id == lesson_id))
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    await db.delete(assignment)
    await db.commit()


# ============ SUBMISSION ROUTES (STUDENT) ============

@router.post("/submissions/upload", status_code=status.HTTP_201_CREATED)
async def upload_submission_file(
    lesson_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)

    # Verify student enrollment
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

    # Get Assignment ID
    result = await db.execute(select(Assignment).where(Assignment.lesson_id == lesson_id))
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    content = await file.read()
    ext = file.filename.split(".")[-1] if "." in file.filename else "bin"
    
    # Key: submissions/{assignment_id}/{student_id}/{uuid}.{ext}
    minio_key = f"submissions/{assignment.id}/{current_user.id}/{uuid.uuid4()}.{ext}"
    
    # Upload to MinIO
    minio_client = MinioClient()
    storage_uri = minio_client.upload_file(content, minio_key, file.content_type)

    try:
        presigned_url = minio_client.get_presigned_url(storage_uri)
    except Exception:
        presigned_url = storage_uri

    return {
        "file_name": file.filename,
        "file_url": presigned_url,
        "file_type": file.content_type,
        "file_size": len(content),
        "storage_key": storage_uri
    }


@router.post("/submissions", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
async def create_submission(
    lesson_id: UUID,
    submission_data: SubmissionCreate,
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
        raise HTTPException(status_code=403, detail="Not enrolled")

    result = await db.execute(select(Assignment).where(Assignment.lesson_id == lesson_id))
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    existing_count = await db.execute(
        select(AssignmentSubmission).where(
            AssignmentSubmission.assignment_id == assignment.id,
            AssignmentSubmission.student_id == current_user.id
        )
    )
    existing_submissions = existing_count.scalars().all()

    if not assignment.allow_resubmit and len(existing_submissions) > 0:
        raise HTTPException(status_code=400, detail="Resubmission not allowed")

    if len(existing_submissions) >= assignment.max_resubmits:
        raise HTTPException(status_code=400, detail="Maximum resubmits reached")

    is_late = False
    if assignment.deadline and datetime.now() > assignment.deadline:
        is_late = True

    submission = AssignmentSubmission(
        assignment_id=assignment.id,
        student_id=current_user.id,
        submission_text=submission_data.submission_text,
        attachments=str(submission_data.attachments) if submission_data.attachments else None,
        is_late=is_late
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)

    submission_dict = {
        "id": submission.id,
        "assignment_id": submission.assignment_id,
        "student_id": submission.student_id,
        "student_name": current_user.full_name,
        "submission_text": submission.submission_text,
        "attachments": _parse_and_presign_attachments(submission.attachments),
        "score": submission.score,
        "feedback": submission.feedback,
        "submitted_at": submission.submitted_at,
        "graded_at": submission.graded_at,
        "is_late": submission.is_late
    }
    return submission_dict


@router.get("/submissions", response_model=List[SubmissionResponse])
async def get_my_submissions(
    lesson_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)

    result = await db.execute(select(Assignment).where(Assignment.lesson_id == lesson_id))
    assignment = result.scalar_one_or_none()
    if not assignment:
        return []

    submissions_result = await db.execute(
        select(AssignmentSubmission)
        .where(AssignmentSubmission.assignment_id == assignment.id)
        .order_by(AssignmentSubmission.submitted_at.desc())
    )
    submissions = submissions_result.scalars().all()

    response = []
    for s in submissions:
        student_result = await db.execute(select(User).where(User.id == s.student_id))
        student = student_result.scalar_one_or_none()
        response.append({
            "id": s.id,
            "assignment_id": s.assignment_id,
            "student_id": s.student_id,
            "student_name": student.full_name if student else None,
            "submission_text": s.submission_text,
            "attachments": _parse_and_presign_attachments(s.attachments),
            "score": s.score,
            "feedback": s.feedback,
            "submitted_at": s.submitted_at,
            "graded_at": s.graded_at,
            "is_late": s.is_late
        })
    return response


# ============ GRADING ROUTES (LECTURER) ============

@router.get("/submissions/all", response_model=List[SubmissionResponse])
async def get_all_submissions(
    lesson_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)

    result = await db.execute(select(Assignment).where(Assignment.lesson_id == lesson_id))
    assignment = result.scalar_one_or_none()
    if not assignment:
        return []

    submissions_result = await db.execute(
        select(AssignmentSubmission)
        .where(AssignmentSubmission.assignment_id == assignment.id)
        .order_by(AssignmentSubmission.submitted_at.desc())
    )
    submissions = submissions_result.scalars().all()

    response = []
    for s in submissions:
        student_result = await db.execute(select(User).where(User.id == s.student_id))
        student = student_result.scalar_one_or_none()
        response.append({
            "id": s.id,
            "assignment_id": s.assignment_id,
            "student_id": s.student_id,
            "student_name": student.full_name if student else None,
            "submission_text": s.submission_text,
            "attachments": _parse_and_presign_attachments(s.attachments),
            "score": s.score,
            "feedback": s.feedback,
            "submitted_at": s.submitted_at,
            "graded_at": s.graded_at,
            "is_late": s.is_late
        })
    return response


@router.post("/submissions/{submission_id}/grade", response_model=SubmissionResponse)
async def grade_submission(
    lesson_id: UUID,
    submission_id: UUID,
    grade_data: SubmissionGrade,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)
    await verify_course_ownership(course, current_user)

    result = await db.execute(
        select(AssignmentSubmission).where(AssignmentSubmission.id == submission_id)
    )
    submission = result.scalar_one_or_none()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    submission.score = grade_data.score
    submission.feedback = grade_data.feedback
    submission.graded_at = datetime.now()

    await db.commit()
    await db.refresh(submission)

    student_result = await db.execute(select(User).where(User.id == submission.student_id))
    student = student_result.scalar_one_or_none()

    return {
        "id": submission.id,
        "assignment_id": submission.assignment_id,
        "student_id": submission.student_id,
        "student_name": student.full_name if student else None,
        "submission_text": submission.submission_text,
        "attachments": _parse_and_presign_attachments(submission.attachments),
        "score": submission.score,
        "feedback": submission.feedback,
        "submitted_at": submission.submitted_at,
        "graded_at": submission.graded_at,
        "is_late": submission.is_late
    }