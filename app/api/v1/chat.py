from fastapi import APIRouter

router = APIRouter()


@router.post("/sessions")
async def create_session():
    pass


@router.get("/sessions")
async def list_sessions():
    pass


@router.delete("/sessions/{session_id}")
async def delete_session():
    pass


@router.post("/ask")
async def ask():
    pass
