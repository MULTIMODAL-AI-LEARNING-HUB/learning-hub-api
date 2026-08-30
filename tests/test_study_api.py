import pytest


@pytest.mark.asyncio
async def test_quiz_generate_unauthorized(client):
    response = await client.post(
        "/api/v1/study/quiz/generate",
        json={"num_questions": 0}
    )
    assert response.status_code in (401, 422)

@pytest.mark.asyncio
async def test_quiz_by_course_unauthorized(client):
    response = await client.post(
        "/api/v1/study/quiz/by-course",
        json={"course_id": "not-a-valid-uuid"}
    )
    assert response.status_code in (401, 422)
