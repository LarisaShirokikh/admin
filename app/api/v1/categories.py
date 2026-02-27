from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.exceptions import raise_404
from app.models.category import Category
from app.schemas.category import CategoryResponse

router = APIRouter()


@router.get("/", response_model=List[CategoryResponse])
@router.get("/list", response_model=List[CategoryResponse])
async def get_categories(
    is_active: Optional[bool] = Query(True),
    db: AsyncSession = Depends(get_db),
):
    query = select(Category).order_by(Category.name)
    if is_active is not None:
        query = query.where(Category.is_active == is_active)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/tree", response_model=List[CategoryResponse])
async def get_category_tree(
    is_active: Optional[bool] = Query(True),
    db: AsyncSession = Depends(get_db),
):
    query = select(Category).order_by(Category.name)
    if is_active is not None:
        query = query.where(Category.is_active == is_active)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{slug}", response_model=CategoryResponse)
async def get_category_by_slug(
    slug: str = Path(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Category).where(Category.slug == slug, Category.is_active == True)
    )
    cat = result.scalar_one_or_none()
    if not cat:
        raise_404(entity="Category", id=slug)
    return cat
