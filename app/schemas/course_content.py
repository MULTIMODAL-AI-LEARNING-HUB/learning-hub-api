from pydantic import BaseModel, Field
from typing import Optional, List, Any
from uuid import UUID
from datetime import datetime


# ============ SECTION SCHEMAS ============

class SectionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    order_index: int = 0


class SectionUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


class SectionResponse(BaseModel):
    id: UUID
    course_id: UUID
    title: str
    description: Optional[str]
    order_index: int
    created_at: datetime
    updated_at: datetime
    lesson_count: int = 0

    class Config:
        from_attributes = True


class SectionWithLessons(BaseModel):
    id: UUID
    course_id: UUID
    title: str
    description: Optional[str]
    order_index: int
    created_at: datetime
    updated_at: datetime
    lessons: List["LessonResponse"] = []

    class Config:
        from_attributes = True


# ============ LESSON SCHEMAS ============

class LessonCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    type: str = "ARTICLE"
    video_url: Optional[str] = None
    video_duration: Optional[int] = None
    content: Optional[str] = None
    order_index: int = 0
    is_preview: bool = False


class LessonUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    type: Optional[str] = None
    video_url: Optional[str] = None
    video_duration: Optional[int] = None
    content: Optional[str] = None
    is_preview: Optional[bool] = None
    is_active: Optional[bool] = None


class LessonResponse(BaseModel):
    id: UUID
    section_id: UUID
    title: str
    description: Optional[str]
    type: str
    video_url: Optional[str]
    video_duration: Optional[int]
    content: Optional[str]
    order_index: int
    is_preview: bool
    is_active: bool
    has_quiz: bool = False
    has_assignment: bool = False
    attachment_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LessonWithContent(LessonResponse):
    quiz: Optional["QuizResponse"] = None
    assignment: Optional["AssignmentResponse"] = None
    attachments: List["AttachmentResponse"] = []


# ============ ATTACHMENT SCHEMAS ============

class AttachmentResponse(BaseModel):
    id: UUID
    lesson_id: UUID
    file_name: str
    file_url: str
    file_type: Optional[str]
    file_size: Optional[int]
    uploaded_at: datetime

    class Config:
        from_attributes = True


class AttachmentCreate(BaseModel):
    file_name: str
    file_url: str
    file_type: Optional[str] = None
    file_size: Optional[int] = None


# ============ QUIZ SCHEMAS ============

class QuizCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    passing_score: int = Field(default=70, ge=0, le=100)
    duration_mins: Optional[int] = None
    max_attempts: int = Field(default=3, ge=1)


class QuizUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    passing_score: Optional[int] = Field(None, ge=0, le=100)
    duration_mins: Optional[int] = None
    max_attempts: Optional[int] = Field(None, ge=1)
    is_active: Optional[bool] = None


class QuizResponse(BaseModel):
    id: UUID
    lesson_id: UUID
    title: str
    description: Optional[str]
    passing_score: int
    duration_mins: Optional[int]
    max_attempts: int
    is_active: bool
    question_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QuizWithQuestions(QuizResponse):
    questions: List["QuestionWithAnswers"] = []


# ============ QUESTION SCHEMAS ============

class QuestionCreate(BaseModel):
    question_text: str = Field(..., min_length=1)
    type: str = "SINGLE_CHOICE"
    points: int = Field(default=1, ge=1)
    explanation: Optional[str] = None
    order_index: int = 0
    answers: List[AnswerCreate] = []


class QuestionUpdate(BaseModel):
    question_text: Optional[str] = None
    type: Optional[str] = None
    points: Optional[int] = None
    explanation: Optional[str] = None


class QuestionResponse(BaseModel):
    id: UUID
    quiz_id: UUID
    question_text: str
    type: str
    points: int
    explanation: Optional[str]
    order_index: int
    created_at: datetime

    class Config:
        from_attributes = True


class QuestionWithAnswers(QuestionResponse):
    answers: List["AnswerResponse"] = []


# ============ ANSWER SCHEMAS ============

class AnswerCreate(BaseModel):
    answer_text: str = Field(..., min_length=1)
    is_correct: bool = False
    order_index: int = 0


class AnswerUpdate(BaseModel):
    answer_text: Optional[str] = None
    is_correct: Optional[bool] = None


class AnswerResponse(BaseModel):
    id: UUID
    question_id: UUID
    answer_text: str
    is_correct: bool
    order_index: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============ QUIZ ATTEMPT SCHEMAS ============

class QuizAttemptStart(BaseModel):
    pass


class QuizAttemptSubmit(BaseModel):
    answers: List[dict] = Field(..., description="List of answers: [{\"question_id\": \"...\", \"selected_answers\": [\"answer_id1\", \"answer_id2\"]}]")


class QuizAttemptResponse(BaseModel):
    id: UUID
    enrollment_id: UUID
    quiz_id: UUID
    attempt_number: int
    score: Optional[float]
    max_score: Optional[float]
    passed: Optional[bool]
    started_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class QuizAttemptResult(QuizAttemptResponse):
    correct_answers: List[dict] = []


# ============ ASSIGNMENT SCHEMAS ============

class AssignmentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    instructions: Optional[str] = None
    deadline: Optional[datetime] = None
    max_score: int = Field(default=100, ge=1)
    allow_resubmit: bool = True
    max_resubmits: int = Field(default=3, ge=0)


class AssignmentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    instructions: Optional[str] = None
    deadline: Optional[datetime] = None
    max_score: Optional[int] = None
    allow_resubmit: Optional[bool] = None
    max_resubmits: Optional[int] = None
    is_active: Optional[bool] = None


class AssignmentResponse(BaseModel):
    id: UUID
    lesson_id: UUID
    title: str
    description: Optional[str]
    instructions: Optional[str]
    deadline: Optional[datetime]
    max_score: int
    allow_resubmit: bool
    max_resubmits: int
    submission_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AssignmentWithSubmissions(AssignmentResponse):
    submissions: List["SubmissionResponse"] = []


# ============ ASSIGNMENT SUBMISSION SCHEMAS ============

class SubmissionCreate(BaseModel):
    submission_text: Optional[str] = None
    attachments: Optional[List[dict]] = None


class SubmissionGrade(BaseModel):
    score: int = Field(..., ge=0)
    feedback: Optional[str] = None


class SubmissionResponse(BaseModel):
    id: UUID
    assignment_id: UUID
    student_id: UUID
    student_name: Optional[str] = None
    submission_text: Optional[str]
    attachments: Optional[List[dict]]
    score: Optional[int]
    feedback: Optional[str]
    submitted_at: datetime
    graded_at: Optional[datetime]
    is_late: bool

    class Config:
        from_attributes = True


# ============ DISCUSSION SCHEMAS ============

class DiscussionCreate(BaseModel):
    content: str = Field(..., min_length=1)
    parent_id: Optional[UUID] = None


class DiscussionUpdate(BaseModel):
    content: Optional[str] = None
    is_pinned: Optional[bool] = None
    is_answer: Optional[bool] = None


class DiscussionResponse(BaseModel):
    id: UUID
    lesson_id: UUID
    user_id: UUID
    user_name: Optional[str] = None
    user_avatar: Optional[str] = None
    parent_id: Optional[UUID]
    content: str
    is_pinned: bool
    is_answer: bool
    upvotes: int
    reply_count: int = 0
    created_at: datetime
    updated_at: datetime
    replies: List["DiscussionResponse"] = []

    class Config:
        from_attributes = True


# ============ REVIEW SCHEMAS ============

class ReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None


class ReviewUpdate(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    comment: Optional[str] = None


class LecturerReply(BaseModel):
    reply: str = Field(..., min_length=1)


class ReviewResponse(BaseModel):
    id: UUID
    enrollment_id: UUID
    rating: int
    comment: Optional[str]
    lecturer_reply: Optional[str]
    replied_at: Optional[datetime]
    created_at: datetime
    student_name: Optional[str] = None
    course_title: Optional[str] = None

    class Config:
        from_attributes = True


# ============ COURSE UPDATE SCHEMAS ============

class CourseContentUpdate(BaseModel):
    level: Optional[str] = None
    language: Optional[str] = None
    requirements: Optional[str] = None
    learning_outcomes: Optional[str] = None
    tags: Optional[str] = None


# ============ DASHBOARD SCHEMAS ============

class DashboardStats(BaseModel):
    total_courses: int
    total_students: int
    total_lessons: int
    pending_submissions: int
    total_revenue: int
    avg_rating: float
    view_count: int


class CourseStats(BaseModel):
    course_id: UUID
    title: str
    enrolled_students: int
    completion_rate: float
    avg_rating: float
    view_count: int
    revenue: int


# ============ REORDER SCHEMAS ============

class ReorderSections(BaseModel):
    section_ids: List[UUID]


class ReorderLessons(BaseModel):
    lesson_ids: List[UUID]


class ReorderQuestions(BaseModel):
    question_ids: List[UUID]


# ============ PAGINATION ============

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


# Update forward references
SectionWithLessons.model_rebuild()
LessonWithContent.model_rebuild()
QuizWithQuestions.model_rebuild()