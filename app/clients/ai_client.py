"""AI service HTTP client."""

from typing import Any

import httpx

from app.core.config import settings


class AiClient:
    def __init__(self) -> None:
        self.base_url = settings.AI_SERVICE_URL.rstrip("/")

    async def ask(self, payload: dict) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=60) as client:
            response = await client.post("/chat/ask", json=payload)
            response.raise_for_status()
            return response.json()
