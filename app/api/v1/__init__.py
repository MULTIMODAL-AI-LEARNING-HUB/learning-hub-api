from fastapi import APIRouter

from app.api.v1 import auth, documents, chat, study, admin

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(study.router, prefix="/study", tags=["study"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
