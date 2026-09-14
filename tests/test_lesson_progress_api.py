import pytest


@pytest.mark.asyncio
async def test_enrollment_progress_unauthorized(client):
    response = await client.get(
        "/api/v1/enrollments/00000000-0000-0000-0000-000000000000/progress"
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_lesson_progress_update_unauthorized(client):
    response = await client.post(
        "/api/v1/enrollments/00000000-0000-0000-0000-000000000000"
        "/lessons/00000000-0000-0000-0000-000000000000/progress",
        json={"completed": True},
    )
    assert response.status_code == 401
