from app.schemas.admin import (
    AdminCourseListResponse,
    AdminCourseResponse,
    AdminUserCreate,
    AdminUserListResponse,
    AdminUserResponse,
    AdminUserUpdate,
)
from app.schemas.auth import (
    AuthResponse,
    AuthUserResponse,
    FacebookLoginRequest,
    ForgotPasswordRequest,
    GoogleLoginRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UpdateProfileRequest,
)
from app.schemas.category import (
    CategoryCreate,
    CategoryResponse,
    CategoryTreeResponse,
    CategoryUpdate,
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
from app.schemas.dashboard import (
    DashboardActivity,
    DashboardCourseProgress,
    DashboardResponse,
    DashboardStats,
)
from app.schemas.documents import (
    DocumentListResponse,
    DocumentResponse,
    DocumentUploadRequest,
    DocumentUploadResponse,
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

__all__ = [
    # Auth
    "AuthResponse",
    "AuthUserResponse",
    "FacebookLoginRequest",
    "ForgotPasswordRequest",
    "GoogleLoginRequest",
    "LoginRequest",
    "LogoutRequest",
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