# app/crud/brand.py
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.brand import Brand
from app.schemas.brand import BrandCreate, BrandUpdate

async def create_brand(db: AsyncSession, brand: BrandCreate) -> Brand:
    """Создание нового бренда"""
    # Автоматическая генерация slug если не указан
    if not brand.slug:
        import re
        slug = re.sub(r'[^a-zA-Z0-9]', '-', brand.name.lower())
        db_brand = Brand(
            name=brand.name,
            slug=slug,
            description=brand.description,
            logo_url=brand.logo_url,
            website=brand.website,
            is_active=brand.is_active
        )
    else:
        db_brand = Brand(
            name=brand.name,
            slug=brand.slug,
            description=brand.description,
            logo_url=brand.logo_url,
            website=brand.website,
            is_active=brand.is_active
        )
    
    db.add(db_brand)
    await db.commit()
    await db.refresh(db_brand)
    return db_brand

async def get_brand(db: AsyncSession, brand_id: int) -> Optional[Brand]:
    """Получение бренда по ID"""
    result = await db.execute(select(Brand).where(Brand.id == brand_id))
    return result.scalar_one_or_none()

async def get_brand_by_slug(db: AsyncSession, slug: str) -> Optional[Brand]:
    """Получение бренда по slug"""
    result = await db.execute(select(Brand).where(Brand.slug == slug))
    return result.scalar_one_or_none()

async def get_brands(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[Brand]:
    """Получение списка брендов"""
    result = await db.execute(select(Brand).offset(skip).limit(limit))
    return result.scalars().all()

async def update_brand(db: AsyncSession, brand_id: int, brand: BrandUpdate) -> Optional[Brand]:
    """Обновление бренда"""
    db_brand = await get_brand(db, brand_id)
    if not db_brand:
        return None
    
    # Обновляем только переданные поля
    update_data = brand.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_brand, key, value)
    
    await db.commit()
    await db.refresh(db_brand)
    return db_brand

async def delete_brand(db: AsyncSession, brand_id: int) -> bool:
    """Удаление бренда"""
    db_brand = await get_brand(db, brand_id)
    if not db_brand:
        return False
    
    await db.delete(db_brand)
    await db.commit()
    return True

