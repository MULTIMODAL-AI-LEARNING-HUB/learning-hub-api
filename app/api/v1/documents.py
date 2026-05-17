from fastapi import APIRouter

router = APIRouter()


@router.post("/upload")
async def upload():
    pass


@router.get("/")
async def list_documents():
    pass


@router.get("/{doc_id}")
async def get_document():
    pass


@router.delete("/{doc_id}")
async def delete_document():
    pass
