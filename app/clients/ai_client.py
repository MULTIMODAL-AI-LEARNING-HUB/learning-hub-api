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
        response = await self.client.post("/chat/ask", json=payload)
        response.raise_for_status()
        return response.json()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def grade_essay(self, document_id: str, essay_text: str) -> dict[str, Any]:
        """Grade essay matching against source document."""
        response = await self.client.post(
            "/study/essay/grade",
            json={
                "document_id": document_id,
                "essay_text": essay_text,
            }
        )
        response.raise_for_status()
        return response.json()
