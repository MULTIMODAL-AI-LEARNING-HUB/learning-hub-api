from fastapi import APIRouter

from app.api.v1 import auth, documents, chat, study, admin, categories, courses, enrollments, progress
from app.api.v1.course_materials import router as course_materials_router
from app.webhooks.payment_webhooks import router as payment_webhooks_router

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(courses.router, prefix="/courses", tags=["courses"])
api_router.include_router(course_materials_router, prefix="/courses")
api_router.include_router(enrollments.router, tags=["enrollments"])
api_router.include_router(progress.router, tags=["progress"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(study.router, prefix="/study", tags=["study"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(payment_webhooks_router)