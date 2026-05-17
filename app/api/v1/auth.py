from fastapi import APIRouter

router = APIRouter()


@router.post("/register")
async def register():
    pass


@router.post("/login")
async def login():
    pass


@router.post("/refresh")
async def refresh():
    pass


@router.get("/me")
async def me():
    pass
