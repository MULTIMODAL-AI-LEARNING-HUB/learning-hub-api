import pytest


@pytest.mark.asyncio
async def test_notes_list_unauthorized(client):
    response = await client.get(
        "/api/v1/notes",
        params={"course_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_notes_create_unauthorized(client):
    response = await client.post(
        "/api/v1/notes",
        json={
            "course_id": "00000000-0000-0000-0000-000000000000",
            "content": "My lesson note",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_notes_update_unauthorized(client):
    response = await client.put(
        "/api/v1/notes/00000000-0000-0000-0000-000000000000",
        json={"content": "Updated content"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_notes_delete_unauthorized(client):
    response = await client.delete("/api/v1/notes/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 401
