"""Category API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import require_admin, get_current_user
from app.dependencies.db import get_db
from app.models.user import User
from app.repositories.category_repo import CategoryRepository
from app.schemas import (
    CategoryCreate,
    CategoryResponse,
    CategoryTreeResponse,
    CategoryUpdate,
)
from app.services.category_service import CategoryService

router = APIRouter()


def _to_response(category) -> CategoryResponse:
    return CategoryResponse(
        id=category.id,
        name=category.name,
        slug=category.slug,
        description=category.description,
        icon=category.icon,
        image_url=category.image_url,
        parent_id=category.parent_id,
        created_at=category.created_at,
    )


def _to_tree_response(category) -> CategoryTreeResponse:
    return CategoryTreeResponse(
        id=category.id,
        name=category.name,
        slug=category.slug,
        description=category.description,
        icon=category.icon,
        image_url=category.image_url,
        children=[_to_tree_response(c) for c in category.children] if hasattr(category, 'children') else [],
    )


@router.get("/", response_model=list[CategoryResponse])
async def list_categories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CategoryResponse]:
    """List all categories."""
    repo = CategoryRepository(db)
    service = CategoryService(repo)
    categories = await service.get_all()
    return [_to_response(c) for c in categories]


@router.get("/tree", response_model=list[CategoryTreeResponse])
async def get_category_tree(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CategoryTreeResponse]:
    """Get category tree structure."""
    repo = CategoryRepository(db)
    service = CategoryService(repo)
    categories = await service.get_tree()
    return [_to_tree_response(c) for c in categories]


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CategoryResponse:
    """Get a category by ID."""
    repo = CategoryRepository(db)
    service = CategoryService(repo)
    category = await service.get_by_id(category_id)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return _to_response(category)


@router.post("/", response_model=CategoryResponse, status_code=201)
async def create_category(
    payload: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> CategoryResponse:
    """Create a new category. Admin only."""
    repo = CategoryRepository(db)
    service = CategoryService(repo)

    existing = await service.get_by_slug(payload.slug)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category slug already exists")

    category = await service.create(
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        icon=payload.icon,
    )
    return _to_response(category)


@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: UUID,
    payload: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> CategoryResponse:
    """Update a category. Admin only."""
    repo = CategoryRepository(db)
    service = CategoryService(repo)

    category = await service.update(
        category_id=category_id,
        name=payload.name,
        description=payload.description,
        icon=payload.icon,
    )
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return _to_response(category)


@router.delete("/{category_id}", status_code=204)
async def delete_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> None:
    """Delete a category. Admin only."""
    repo = CategoryRepository(db)
    service = CategoryService(repo)
    await service.delete(category_id)