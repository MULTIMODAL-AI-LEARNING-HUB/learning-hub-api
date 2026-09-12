from uuid import UUID
from pydantic import BaseModel


class AudioSummaryResponse(BaseModel):
    lesson_id: UUID
    lesson_title: str
    audio_url: str
    voice: str
    is_cached: bool = False
