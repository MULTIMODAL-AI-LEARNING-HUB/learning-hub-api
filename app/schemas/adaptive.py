from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MissedQuestionItem(BaseModel):
    question_id: str
    question_text: str
    selected_answers: List[str] = []
    correct_answers: List[str] = []
    explanation: Optional[str] = None
    is_correct: bool = False


class WeaknessAreaItem(BaseModel):
    lesson_id: UUID
    lesson_title: str
    course_id: UUID
    course_title: str
    total_questions: int
    missed_count: int
    accuracy_percent: float
    last_attempt_at: Optional[datetime] = None
    missed_questions: List[MissedQuestionItem] = []


class WeaknessSummaryResponse(BaseModel):
    weaknesses: List[WeaknessAreaItem]
    total_weak_areas: int


class RemedialQuizGenerateRequest(BaseModel):
    question_count: int = Field(default=3, ge=1, le=10)


class RemedialQuestionResponse(BaseModel):
    id: str
    question: str
    options: List[str]
    correct_answer: str
    explanation: Optional[str] = None


class RemedialQuizResponse(BaseModel):
    lesson_id: UUID
    lesson_title: str
    target_weaknesses_count: int
    questions: List[RemedialQuestionResponse]
