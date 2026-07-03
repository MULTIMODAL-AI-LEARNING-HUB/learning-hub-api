from app.schemas.auth import (
    AuthResponse,
    AuthUserResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UpdateProfileRequest,
)
from app.schemas.documents import (
    DocumentListResponse,
    DocumentResponse,
    DocumentUploadRequest,
    DocumentUploadResponse,
)
from app.schemas.chat import (
    ChatAskRequest,
    ChatMessageResponse,
    ChatMessagesResponse,
    ChatSessionCreateRequest,
    ChatSessionListItem,
    ChatSessionListResponse,
    ChatSessionResponse,
)
from app.schemas.category import (
    CategoryCreate,
    CategoryResponse,
    CategoryTreeResponse,
    CategoryUpdate,
)
from app.schemas.course import (
    CourseCreate,
    CourseDetailResponse,
    CourseListResponse,
    CourseResponse,
    CourseUpdate,
)
from app.schemas.course_material import (
    CourseMaterialCreate,
    CourseMaterialListResponse,
    CourseMaterialResponse,
    CourseMaterialUpdate,
)
from app.schemas.enrollment import (
    EnrollmentListResponse,
    EnrollmentResponse,
    EnrollmentWithCourseResponse,
    PaymentConfirmRequest,
    PaymentIntentRequest,
    PaymentIntentResponse,
)
from app.schemas.progress import (
    EnrollmentProgressResponse,
    MaterialProgressResponse,
    MaterialProgressUpdate,
)
from app.schemas.admin import (
    AdminUserCreate,
    AdminUserUpdate,
    AdminUserResponse,
    AdminUserListResponse,
    AdminCourseResponse,
    AdminCourseListResponse,
)
from app.schemas.dashboard import (
    DashboardResponse,
    DashboardCourseProgress,
    DashboardStats,
    DashboardActivity,
)

__all__ = [
    # Auth
    "AuthResponse",
    "AuthUserResponse",
    "ForgotPasswordRequest",
    "LoginRequest",
    "MessageResponse",
    "RefreshRequest",
    "RegisterRequest",
    "ResetPasswordRequest",
    "TokenResponse",
    "UpdateProfileRequest",
    # Documents
    "DocumentListResponse",
    "DocumentResponse",
    "DocumentUploadRequest",
    "DocumentUploadResponse",
    # Chat
    "ChatAskRequest",
    "ChatMessageResponse",
    "ChatMessagesResponse",
    "ChatSessionCreateRequest",
    "ChatSessionListItem",
    "ChatSessionListResponse",
    "ChatSessionResponse",
    # Category
    "CategoryCreate",
    "CategoryResponse",
    "CategoryTreeResponse",
    "CategoryUpdate",
    # Course
    "CourseCreate",
    "CourseDetailResponse",
    "CourseListResponse",
    "CourseResponse",
    "CourseUpdate",
    # CourseMaterial
    "CourseMaterialCreate",
    "CourseMaterialListResponse",
    "CourseMaterialResponse",
    "CourseMaterialUpdate",
    # Enrollment
    "EnrollmentListResponse",
    "EnrollmentResponse",
    "EnrollmentWithCourseResponse",
    "PaymentConfirmRequest",
    "PaymentIntentRequest",
    "PaymentIntentResponse",
    # Progress
    "EnrollmentProgressResponse",
    "MaterialProgressResponse",
    "MaterialProgressUpdate",
    # Admin
    "AdminUserCreate",
    "AdminUserUpdate",
    "AdminUserResponse",
    "AdminUserListResponse",
    "AdminCourseResponse",
    "AdminCourseListResponse",
    # Dashboard
    "DashboardResponse",
    "DashboardCourseProgress",
    "DashboardStats",
    "DashboardActivity",
]