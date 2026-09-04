import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_readiness_probe_healthy(client):
    mock_redis = AsyncMock()
    mock_redis.ping.return_value = True

    mock_session = AsyncMock()
    mock_session.execute.return_value = None

    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__.return_value = mock_session
    mock_session_ctx.__aexit__.return_value = None

    with patch("app.main.get_redis_client", return_value=mock_redis), \
         patch("app.core.database.AsyncSessionLocal", return_value=mock_session_ctx):
        response = await client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["dependencies"]["redis"] == "healthy"
        assert data["dependencies"]["database"] == "healthy"


@pytest.mark.asyncio
async def test_readiness_probe_degraded(client):
    mock_redis = AsyncMock()
    mock_redis.ping.side_effect = ConnectionError("Redis down")

    with patch("app.main.get_redis_client", return_value=mock_redis):
        response = await client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert "unhealthy" in data["dependencies"]["redis"]

