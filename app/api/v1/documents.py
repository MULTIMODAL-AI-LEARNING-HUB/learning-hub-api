from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.document import Document
from app.models.user import User
from app.repositories.document_repo import DocumentRepository
from app.schemas import DocumentListResponse, DocumentResponse, DocumentUploadResponse
from app.tasks.document_tasks import dispatch_process_document
from app.utils.pagination import build_pagination

router = APIRouter()


def _to_response(doc: Document) -> DocumentResponse:
    return DocumentResponse(
        id=doc.id,
        file_name=doc.file_name,
        file_type=doc.file_type,
        file_url=doc.file_url,
        file_size=doc.file_size,
        status=doc.status,
        metadata=doc.file_metadata,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.post("/upload", response_model=DocumentUploadResponse, status_code=202)
async def upload(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentUploadResponse:
    repo = DocumentRepository(db)
    document = Document(
        user_id=current_user.id,
        file_name=file.filename or "uploaded",
        file_type=(file.content_type or "application/octet-stream").split("/")[-1],
        file_url=f"s3://{file.filename}",
        file_size=None,
        status="processing",
    )
    document = await repo.create(document)
    dispatch_process_document(str(document.id))
    return DocumentUploadResponse(
        id=document.id,
        file_name=document.file_name,
        file_type=document.file_type,
        file_size=document.file_size,
        status=document.status,
        created_at=document.created_at,
    )


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentListResponse:
    repo = DocumentRepository(db)
    offset = (page - 1) * page_size
    docs = await repo.list_by_user(current_user.id, offset, page_size)
    total = await repo.count_by_user(current_user.id)
    pagination = build_pagination(total, page, page_size)
    return DocumentListResponse(
        items=[_to_response(d) for d in docs],
        total=pagination["total"],
        page=pagination["page"],
        page_size=pagination["page_size"],
    )


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentResponse:
    repo = DocumentRepository(db)
    doc = await repo.get_by_id(doc_id)
    if not doc or doc.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return _to_response(doc)


@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    repo = DocumentRepository(db)
    doc = await repo.get_by_id(doc_id)
    if not doc or doc.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    await repo.delete(doc_id)
