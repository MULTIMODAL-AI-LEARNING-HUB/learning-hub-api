"""Audio TTS Summary API endpoints.

Generates Vietnamese text-to-speech summaries of lessons using edge-tts,
caches the result URL in lessons.audio_summary_url to avoid redundant generation.
"""

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.minio_client import MinioClient
from app.dependencies.auth import get_current_user
from app.dependencies.course_auth import get_lesson_with_course, verify_lesson_access
from app.dependencies.db import get_db
from app.models.user import User
from app.schemas.audio import AudioSummaryResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# Edge-TTS voice selection
VOICE_FEMALE = "vi-VN-HoaiMyNeural"
VOICE_MALE = "vi-VN-NamMinhNeural"


def _build_summary_script(lesson) -> str:
    """Build a concise TTS-friendly summary from lesson fields."""
    parts = [f"Tóm tắt bài học: {lesson.title}."]

    if lesson.description and lesson.description.strip():
        desc = lesson.description.strip()[:500]
        parts.append(desc)

    if lesson.content and lesson.content.strip():
        # Take up to 1200 chars of content for summary
        content_preview = lesson.content.strip()[:1200]
        # Break at last full stop to avoid cutting mid-sentence
        last_dot = content_preview.rfind('.')
        if last_dot > 200:
            content_preview = content_preview[:last_dot + 1]
        parts.append(content_preview)

    if len(parts) == 1:
        parts.append("Bài học này chưa có nội dung chi tiết. Hãy xem video hoặc tài liệu đính kèm để tìm hiểu.")

    parts.append("Kết thúc phần tóm tắt âm thanh bài học.")
    return " ".join(parts)


async def _generate_tts_audio(text: str, voice: str = VOICE_FEMALE) -> bytes:
    """Generate audio bytes from text via edge-tts."""
    try:
        import edge_tts
    except ImportError:
        raise RuntimeError("edge-tts library is not installed")

    communicate = edge_tts.Communicate(text, voice)
    chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    if not chunks:
        raise RuntimeError("edge-tts returned empty audio stream")
    return b"".join(chunks)


def _upload_audio(audio_bytes: bytes, lesson_id: str) -> str:
    """Upload audio bytes to MinIO and return storage key / public URL."""
    minio = MinioClient()
    key = f"audio_summaries/{lesson_id}.mp3"
    storage_uri = minio.upload_file(audio_bytes, key, content_type="audio/mpeg")
    return storage_uri


@router.get("/lessons/{lesson_id}/audio-summary", response_model=AudioSummaryResponse)
async def get_lesson_audio_summary(
    lesson_id: UUID,
    voice: str = "female",
    regenerate: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AudioSummaryResponse:
    """Get or generate the Vietnamese TTS audio summary for a lesson.

    Results are cached in lessons.audio_summary_url.
    Pass regenerate=true to force a fresh generation.
    voice: "female" (default, HoaiMy) or "male" (NamMinh)
    """
    lesson, course = await get_lesson_with_course(db, lesson_id)
    await verify_lesson_access(lesson, course, current_user, db)

    selected_voice = VOICE_MALE if voice == "male" else VOICE_FEMALE

    # Return cached audio URL if available and not forcing regeneration
    if lesson.audio_summary_url and lesson.audio_summary_url.strip() and not regenerate:
        return AudioSummaryResponse(
            lesson_id=lesson.id,
            lesson_title=lesson.title,
            audio_url=lesson.audio_summary_url,
            voice=selected_voice,
            is_cached=True,
        )

    # Build TTS script
    script = _build_summary_script(lesson)

    try:
        # Generate audio bytes
        audio_bytes = await _generate_tts_audio(script, selected_voice)
    except Exception as exc:
        logger.error("Failed to generate TTS audio for lesson %s: %s", lesson_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Không thể tạo âm thanh tóm tắt. Vui lòng thử lại sau.",
        )

    try:
        storage_uri = await asyncio.to_thread(_upload_audio, audio_bytes, str(lesson_id))
    except Exception as exc:
        logger.error("Failed to upload TTS audio for lesson %s: %s", lesson_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Không thể lưu trữ file âm thanh. Vui lòng thử lại sau.",
        )

    # Resolve public URL from storage URI
    minio = MinioClient()
    if storage_uri.startswith("s3://"):
        audio_url = minio.get_presigned_url(storage_uri, expires_seconds=86400)
    else:
        # Local fallback — expose via an API route
        audio_url = f"/api/v1/audio/lessons/{lesson_id}/stream"

    # Cache in DB
    lesson.audio_summary_url = audio_url
    await db.commit()
    await db.refresh(lesson)

    return AudioSummaryResponse(
        lesson_id=lesson.id,
        lesson_title=lesson.title,
        audio_url=audio_url,
        voice=selected_voice,
        is_cached=False,
    )
