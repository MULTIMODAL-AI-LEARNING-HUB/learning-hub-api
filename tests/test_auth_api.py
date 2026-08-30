import pytest


@pytest.mark.asyncio
async def test_register_invalid_email(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "invalid-email-format",
            "password": "Password123!",
            "full_name": "Test User"
        }
    )
    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "validation_error"

@pytest.mark.asyncio
async def test_login_missing_credentials(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={}
    )
    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "validation_error"
