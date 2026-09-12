from uuid import UUID
from pydantic import BaseModel, Field


class LessonMindmapResponse(BaseModel):
    lesson_id: UUID
    lesson_title: str
    markdown_tree: str
    is_cached: bool = False


class TextMindmapRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    title: str = Field(default="", max_length=255)


class TextMindmapResponse(BaseModel):
    markdown_tree: str
