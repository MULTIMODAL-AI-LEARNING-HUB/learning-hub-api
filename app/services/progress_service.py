"""Progress service."""

from uuid import UUID

from app.models.material_progress import MaterialProgress
from app.repositories.course_material_repo import CourseMaterialRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.progress_repo import ProgressRepository


class ProgressService:
    COMPLETION_THRESHOLD = 80

    def __init__(
        self,
        progress_repo: ProgressRepository,
        material_repo: CourseMaterialRepository,
        enrollment_repo: EnrollmentRepository
    ):
        self.progress_repo = progress_repo
        self.material_repo = material_repo
        self.enrollment_repo = enrollment_repo

    async def update_material_progress(
        self,
        enrollment_id: UUID,
        material_id: UUID,
        completion_percent: int,
        last_position: dict | None = None
    ) -> MaterialProgress:
        return await self.progress_repo.update_progress(
            enrollment_id=enrollment_id,
            material_id=material_id,
            completion_percent=completion_percent,
            last_position=last_position
        )

    async def get_enrollment_progress(self, enrollment_id: UUID) -> list[MaterialProgress]:
        return await self.progress_repo.get_enrollment_progress(enrollment_id)

    async def get_material_progress(self, enrollment_id: UUID, material_id: UUID) -> MaterialProgress | None:
        return await self.progress_repo.get_material_progress(enrollment_id, material_id)

    async def get_course_completion_percent(
        self,
        enrollment_id: UUID
    ) -> float:
        enrollment = await self.enrollment_repo.get_by_id(enrollment_id)
        if not enrollment:
            return 0.0

        total_materials = await self.material_repo.count_by_course(enrollment.course_id)
        if total_materials == 0:
            return 0.0

        completed_count = await self.progress_repo.count_completed(enrollment_id)
        return (completed_count / total_materials) * 100

    async def is_enrollment_complete(self, enrollment_id: UUID) -> bool:
        enrollment = await self.enrollment_repo.get_by_id(enrollment_id)
        if not enrollment:
            return False

        total_materials = await self.material_repo.count_by_course(enrollment.course_id)
        if total_materials == 0:
            return False

        completed_count = await self.progress_repo.count_completed(enrollment_id)
        return completed_count == total_materials