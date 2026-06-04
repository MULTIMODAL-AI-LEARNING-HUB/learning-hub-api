"""Redis cache helper module."""

import json
from typing import Any, Optional
import redis.asyncio as aioredis
from app.core.config import settings

# Global Redis connection pool
_redis_client: Optional[aioredis.Redis] = None


def get_redis_client() -> aioredis.Redis:
    """Get or initialize the shared async Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=50
        )
    return _redis_client


async def close_redis() -> None:
    """Close the shared Redis client connection pool."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


class RedisCache:
    """Singleton cache service to store/retrieve JSON serializable data in Redis."""

    def __init__(self) -> None:
        self.redis = get_redis_client()

    async def get(self, key: str) -> Optional[Any]:
        """Get cached item by key, parsing it from JSON."""
        try:
            val = await self.redis.get(key)
            if val:
                return json.loads(val)
        except Exception:
            pass  # Fail-safe caching
        return None

    async def set(self, key: str, value: Any, ttl: int = 60) -> bool:
        """Store item in cache with TTL, serializing to JSON."""
        try:
            val = json.dumps(value)
            await self.redis.set(key, val, ex=ttl)
            return True
        except Exception:
            return False

    async def delete(self, key: str) -> bool:
        """Delete specific key from cache."""
        try:
            await self.redis.delete(key)
            return True
        except Exception:
            return False

    async def delete_pattern(self, pattern: str) -> bool:
        """Delete keys matching pattern."""
        try:
            keys = await self.redis.keys(pattern)
            if keys:
                await self.redis.delete(*keys)
            return True
        except Exception:
            return False

    # Cache key builders
    @staticmethod
    def cache_key_docs(user_id: Any) -> str:
        return f"cache:docs:{user_id}"

    @staticmethod
    def cache_key_sessions(user_id: Any) -> str:
        return f"cache:sessions:{user_id}"

    @staticmethod
    def cache_key_profile(user_id: Any) -> str:
        return f"cache:profile:{user_id}"

    @staticmethod
    def cache_key_quiz_job(job_id: Any) -> str:
        return f"cache:quiz_job:{job_id}"
