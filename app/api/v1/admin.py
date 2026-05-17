from fastapi import APIRouter

router = APIRouter()


@router.get("/users")
async def list_users():
    pass


@router.get("/analytics")
async def analytics():
    pass


@router.get("/health")
async def health():
    pass
