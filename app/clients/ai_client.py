"""AI service HTTP client."""

from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

# Global client instances for pool reuse
_http_client: Optional[httpx.AsyncClient] = None


def get_ai_client() -> httpx.AsyncClient:
    """Get or initialize the shared async HTTP client for the AI service."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            base_url=settings.AI_SERVICE_URL.rstrip("/"),
            timeout=float(settings.AI_SERVICE_TIMEOUT),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
        )
    return _http_client


async def close_ai_client() -> None:
    """Close the shared async HTTP client on application shutdown."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


class AiClient:
    """Wrapper to interact with the learning-hub-ai service."""

    def __init__(self) -> None:
        self.client = get_ai_client()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def ask(self, payload: dict) -> dict[str, Any]:
        """Send chat query to AI service."""
        headers = {"X-Internal-API-Key": settings.INTERNAL_API_KEY}
        response = await self.client.post("/chat/ask", json=payload, headers=headers)
        response.raise_for_status()
        return response.json()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def grade_essay(self, document_id: str, essay_text: str, user_id: str | None = None) -> dict[str, Any]:
        """Grade essay matching against source document."""
        headers = {"X-Internal-API-Key": settings.INTERNAL_API_KEY}
        response = await self.client.post(
            "/study/essay/grade",
            json={
                "document_id": document_id,
                "user_id": user_id,
                "essay_text": essay_text,
            },
            headers=headers
        )
        response.raise_for_status()
        return response.json()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def generate_quiz_from_lesson(
        self,
        lesson_id: str,
        course_id: str,
        question_count: int = 5,
        lesson_content: str | None = ""
    ) -> dict[str, Any]:
        """Request AI service to generate a quiz from lesson resources."""
        headers = {"X-Internal-API-Key": settings.INTERNAL_API_KEY}
        payload = {
            "lesson_id": lesson_id,
            "course_id": course_id,
            "question_count": question_count,
            "lesson_content": lesson_content or ""
        }
        response = await self.client.post("/study/quiz/generate-from-lesson", json=payload, headers=headers)
        response.raise_for_status()
        return response.json()

    async def sync_keys(self, keys: list[dict[str, Any]]) -> dict[str, Any]:
        """Synchronize active AI API keys to the AI service."""
        headers = {"X-Internal-API-Key": settings.INTERNAL_API_KEY}
        try:
            response = await self.client.post("/internal/keys/sync", json={"keys": keys}, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception:
            return {"synced": False}

