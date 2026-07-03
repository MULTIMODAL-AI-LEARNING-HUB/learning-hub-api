from fastapi import APIRouter

from app.api.v1 import auth, documents, chat, study, admin, categories, courses, enrollments, progress
from app.api.v1.course_materials import router as course_materials_router
from app.api.v1.sections import router as sections_router
from app.api.v1.lessons import router as lessons_router
from app.api.v1.quizzes import router as quizzes_router
from app.api.v1.assignments import router as assignments_router
from app.api.v1.discussions import router as discussions_router
from app.api.v1.reviews import router as reviews_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.wishlist import router as wishlist_router
from app.api.v1.announcements import router as announcements_router
from app.api.v1.dashboard import router as dashboard_router
from app.webhooks.payment_webhooks import router as payment_webhooks_router

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(courses.router, prefix="/courses", tags=["courses"])
api_router.include_router(course_materials_router, prefix="/courses")
api_router.include_router(sections_router)
api_router.include_router(lessons_router)
api_router.include_router(quizzes_router, tags=["Quizzes"])
api_router.include_router(assignments_router, tags=["Assignments"])
api_router.include_router(discussions_router, tags=["Discussions"])
api_router.include_router(reviews_router, prefix="/courses", tags=["reviews"])
api_router.include_router(enrollments.router, tags=["enrollments"])
api_router.include_router(progress.router, tags=["progress"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(study.router, prefix="/study", tags=["study"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(notifications_router, prefix="/notifications", tags=["notifications"])
api_router.include_router(wishlist_router, prefix="/wishlist", tags=["wishlist"])
api_router.include_router(announcements_router, tags=["announcements"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(payment_webhooks_router)