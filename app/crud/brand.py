import logging
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.schemas.brand import BrandCreate, BrandUpdate
from app.utils.slug import generate_slug

logger = logging.getLogger(__name__)


async def create_brand(db: AsyncSession, brand: BrandCreate) -> Brand:
    slug = brand.slug
    if not slug:
        slug = generate_slug(brand.name)
        counter = 1
        original_slug = slug
        while await get_brand_by_slug(db, slug):
            slug = f"{original_slug}-{counter}"
            counter += 1

    db_brand = Brand(
        name=brand.name,
        slug=slug,
        description=brand.description,
        logo_url=str(brand.logo_url) if brand.logo_url else None,
        website=str(brand.website) if brand.website else None,
        is_active=brand.is_active,
    )

    try:
        db.add(db_brand)
        await db.commit()
        await db.refresh(db_brand)
        return db_brand
    except IntegrityError:
        await db.rollback()
        raise ValueError(f"Brand with slug '{slug}' already exists")


async def get_brand(db: AsyncSession, brand_id: int) -> Optional[Brand]:
    result = await db.execute(select(Brand).where(Brand.id == brand_id))
    return result.scalar_one_or_none()


async def get_brand_by_slug(db: AsyncSession, slug: str) -> Optional[Brand]:
    result = await db.execute(select(Brand).where(Brand.slug == slug))
    return result.scalar_one_or_none()


async def get_brands(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False,
    search: Optional[str] = None,
) -> List[Brand]:
    query = select(Brand)
    if active_only:
        query = query.where(Brand.is_active == True)
    if search:
        pattern = f"%{search}%"
        query = query.where(Brand.name.ilike(pattern) | Brand.description.ilike(pattern))
    query = query.order_by(Brand.name).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_brand(db: AsyncSession, brand_id: int, brand: BrandUpdate) -> Optional[Brand]:
    db_brand = await get_brand(db, brand_id)
    if not db_brand:
        return None

    update_data = brand.model_dump(exclude_unset=True)

    if "logo_url" in update_data and update_data["logo_url"]:
        update_data["logo_url"] = str(update_data["logo_url"])
    if "website" in update_data and update_data["website"]:
        update_data["website"] = str(update_data["website"])

    if "name" in update_data and not update_data.get("slug"):
        new_slug = generate_slug(update_data["name"])
        if new_slug != db_brand.slug:
            counter = 1
            original = new_slug
            while await get_brand_by_slug(db, new_slug) and new_slug != db_brand.slug:
                new_slug = f"{original}-{counter}"
                counter += 1
            update_data["slug"] = new_slug

    try:
        for key, value in update_data.items():
            setattr(db_brand, key, value)
        await db.commit()
        await db.refresh(db_brand)
        return db_brand
    except IntegrityError:
        await db.rollback()
        raise ValueError(f"Brand with slug '{update_data.get('slug', '')}' already exists")


async def delete_brand(db: AsyncSession, brand_id: int) -> bool:
    db_brand = await get_brand(db, brand_id)
    if not db_brand:
        return False
    try:
        await db.delete(db_brand)
        await db.commit()
        return True
    except IntegrityError:
        await db.rollback()
        db_brand.is_active = False
        await db.commit()
        return True


async def get_brands_count(db: AsyncSession, active_only: bool = False) -> int:
    query = select(func.count(Brand.id))
    if active_only:
        query = query.where(Brand.is_active == True)
    result = await db.execute(query)
    return result.scalar()


async def check_slug_exists(db: AsyncSession, slug: str, exclude_id: Optional[int] = None) -> bool:
    query = select(Brand.id).where(Brand.slug == slug)
    if exclude_id:
        query = query.where(Brand.id != exclude_id)
    result = await db.execute(query)
    return result.scalar_one_or_none() is not None