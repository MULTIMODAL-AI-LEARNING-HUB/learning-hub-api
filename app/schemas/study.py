"""Study tool schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class QuizGenerateRequest(BaseModel):
    document_id: UUID
    quiz_type: str = Field(default="quick", pattern="^(quick|detailed)$")
    question_count: int = Field(default=10, ge=5, le=20)


class QuizGenerateByCourseRequest(BaseModel):
    course_id: UUID
    material_ids: list[UUID] | None = None
    quiz_type: str = Field(default="quick", pattern="^(quick|detailed)$")
    question_count: int = Field(default=10, ge=5, le=20)


class QuizJobResponse(BaseModel):
    job_id: str
    status: str = "processing"


class QuizAnswerItem(BaseModel):
    question_id: UUID
    answer: str = Field(pattern="^[A-D]$")


class QuizSubmitRequest(BaseModel):
    answers: list[QuizAnswerItem]


class QuizQuestionResponse(BaseModel):
    id: UUID
    question: str
    options: list[str]
    correct_answer: str


class QuizResponse(BaseModel):
    id: UUID
    document_id: UUID
    quiz_type: str
    status: str
    questions: list[QuizQuestionResponse]
    created_at: datetime


class QuizResultItem(BaseModel):
    question_id: UUID
    correct: bool
    correct_answer: str
    your_answer: str


class QuizResultResponse(BaseModel):
    score: int
    total: int
    percentage: float
    results: list[QuizResultItem]


class FlashcardGenerateRequest(BaseModel):
    document_id: UUID
    set_name: str = Field(max_length=255)
    count: int = Field(default=20, ge=10, le=50)


class FlashcardItemResponse(BaseModel):
    id: UUID
    front: str
    back: str
    last_reviewed: datetime | None = None


class FlashcardResponse(BaseModel):
    id: UUID
    set_name: str | None = None
    document_id: UUID | None = None
    items: list[FlashcardItemResponse]
    created_at: datetime


class EssaySubmitRequest(BaseModel):
    document_id: UUID
    essay_text: str = Field(min_length=1, max_length=50000)


class EssayComparison(BaseModel):
    student_point: str
    source_match: str
    similarity: float
    assessment: str


class EssayResponse(BaseModel):
    submission_id: UUID
    score: float
    max_score: float = 10
    feedback: str
    comparisons: list[EssayComparison]
    graded_at: datetime
