from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.exceptions import raise_404
from app.models.brand import Brand
from app.models.catalog import Catalog
from app.schemas.brand import BrandResponse

router = APIRouter()


@router.get("/", response_model=List[BrandResponse])
@router.get("/list", response_model=List[BrandResponse])
async def get_brands(
    is_active: Optional[bool] = Query(True),
    db: AsyncSession = Depends(get_db),
):
    query = select(Brand).order_by(Brand.name)
    if is_active is not None:
        query = query.where(Brand.is_active == is_active)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{slug}", response_model=BrandResponse)
async def get_brand_by_slug(
    slug: str = Path(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Brand).where(and_(Brand.slug == slug, Brand.is_active == True))
    )
    brand = result.scalar_one_or_none()
    if not brand:
        raise_404(entity="Brand", id=slug)
    return brand


@router.get("/{slug}/with-catalogs")
async def get_brand_with_catalogs(
    slug: str = Path(...),
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Brand).where(and_(Brand.slug == slug, Brand.is_active == True))
    )
    brand = result.scalar_one_or_none()
    if not brand:
        raise_404(entity="Brand", id=slug)

    count_query = select(func.count(Catalog.id)).where(
        and_(Catalog.brand_id == brand.id, Catalog.is_active == True)
    )
    total = (await db.execute(count_query)).scalar() or 0
    pages = (total + per_page - 1) // per_page

    offset = (page - 1) * per_page
    catalogs_result = await db.execute(
        select(Catalog)
        .where(and_(Catalog.brand_id == brand.id, Catalog.is_active == True))
        .order_by(Catalog.name)
        .offset(offset)
        .limit(per_page)
    )

    return {
        "brand": BrandResponse.model_validate(brand).model_dump(),
        "catalogs": catalogs_result.scalars().all(),
        "total": total,
        "pages": pages,
        "pagination": {"page": page, "per_page": per_page, "total": total, "pages": pages},
    }
