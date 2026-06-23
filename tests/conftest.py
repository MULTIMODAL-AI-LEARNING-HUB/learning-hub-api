import os
import pytest
from httpx import AsyncClient, ASGITransport

# Set mock environment variables for tests (prevents Pydantic validation errors in CI/test environments)
os.environ["DEBUG"] = "True"
os.environ["SECRET_KEY"] = "mock_secret_key_for_testing_purposes_only_12345"
os.environ["INTERNAL_API_KEY"] = "mock_internal_api_key_for_testing_purposes_only_12345"

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
