import logging
from typing import List, Optional

from sqlalchemy import func, select, delete as sa_delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Catalog
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.attributes import product_categories
from app.schemas.catalog import CatalogCreate, CatalogUpdate
from app.utils.slug import generate_slug

logger = logging.getLogger(__name__)


async def _ensure_unique_slug(db: AsyncSession, slug: str, exclude_id: Optional[int] = None) -> str:
    original = slug
    counter = 1
    while True:
        query = select(Catalog.id).where(Catalog.slug == slug)
        if exclude_id:
            query = query.where(Catalog.id != exclude_id)
        result = await db.execute(query)
        if not result.scalar_one_or_none():
            return slug
        slug = f"{original}-{counter}"
        counter += 1


async def create_catalog(db: AsyncSession, data: CatalogCreate) -> Catalog:
    slug = data.slug or generate_slug(data.name)
    slug = await _ensure_unique_slug(db, slug)

    catalog_data = data.model_dump()
    catalog_data["slug"] = slug

    obj = Catalog(**catalog_data)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def get_catalog(db: AsyncSession, catalog_id: int) -> Optional[Catalog]:
    result = await db.execute(select(Catalog).where(Catalog.id == catalog_id))
    return result.scalar_one_or_none()


async def get_catalog_by_slug(db: AsyncSession, slug: str) -> Optional[Catalog]:
    result = await db.execute(select(Catalog).where(Catalog.slug == slug))
    return result.scalar_one_or_none()


async def get_catalogs(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False,
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    brand_id: Optional[int] = None,
) -> List[Catalog]:
    query = select(Catalog)
    if active_only:
        query = query.where(Catalog.is_active == True)
    if search:
        pattern = f"%{search}%"
        query = query.where(Catalog.name.ilike(pattern) | Catalog.description.ilike(pattern))
    if category_id:
        query = query.where(Catalog.category_id == category_id)
    if brand_id:
        query = query.where(Catalog.brand_id == brand_id)
    query = query.order_by(Catalog.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_catalog(db: AsyncSession, catalog_id: int, data: CatalogUpdate) -> Optional[Catalog]:
    existing = await get_catalog(db, catalog_id)
    if not existing:
        return None

    update_data = data.model_dump(exclude_unset=True)

    if "slug" in update_data and update_data["slug"]:
        update_data["slug"] = await _ensure_unique_slug(db, update_data["slug"], catalog_id)
    elif "name" in update_data and not update_data.get("slug"):
        new_slug = generate_slug(update_data["name"])
        update_data["slug"] = await _ensure_unique_slug(db, new_slug, catalog_id)

    if update_data:
        for key, value in update_data.items():
            setattr(existing, key, value)
        await db.commit()
        await db.refresh(existing)

    return existing


async def delete_catalog(db: AsyncSession, catalog_id: int) -> bool:
    existing = await get_catalog(db, catalog_id)
    if not existing:
        return False
    query = sa_delete(Catalog).where(Catalog.id == catalog_id)
    result = await db.execute(query)
    await db.commit()
    return result.rowcount > 0


async def toggle_status(db: AsyncSession, catalog_id: int) -> Optional[Catalog]:
    catalog = await get_catalog(db, catalog_id)
    if not catalog:
        return None
    return await update_catalog(db, catalog_id, CatalogUpdate(is_active=not catalog.is_active))


async def get_stats(db: AsyncSession) -> dict:
    total = (await db.execute(select(func.count(Catalog.id)))).scalar() or 0
    active = (await db.execute(
        select(func.count(Catalog.id)).where(Catalog.is_active == True)
    )).scalar() or 0
    return {
        "total_catalogs": total,
        "active_catalogs": active,
        "inactive_catalogs": total - active,
    }


async def delete_catalog(db: AsyncSession, catalog_id: int) -> bool:
    """Удаляет каталог вместе со всеми продуктами."""
    existing = await get_catalog(db, catalog_id)
    if not existing:
        return False

    # Получаем ID продуктов каталога
    result = await db.execute(select(Product.id).where(Product.catalog_id == catalog_id))
    product_ids = [row[0] for row in result.all()]

    if product_ids:
        await db.execute(text("DELETE FROM videos WHERE product_id = ANY(:ids)"), {"ids": product_ids})
        await db.execute(text("DELETE FROM reviews WHERE product_id = ANY(:ids)"), {"ids": product_ids})
        await db.execute(sa_delete(ProductImage).where(ProductImage.product_id.in_(product_ids)))
        await db.execute(sa_delete(product_categories).where(product_categories.c.product_id.in_(product_ids)))
        await db.execute(sa_delete(Product).where(Product.catalog_id == catalog_id))

    await db.execute(sa_delete(Catalog).where(Catalog.id == catalog_id))
    await db.commit()
    return True


async def batch_delete(db: AsyncSession, catalog_ids: List[int]) -> int:
    """Удаляет несколько каталогов с продуктами."""
    result = await db.execute(select(Product.id).where(Product.catalog_id.in_(catalog_ids)))
    product_ids = [row[0] for row in result.all()]

    if product_ids:
        await db.execute(text("DELETE FROM videos WHERE product_id = ANY(:ids)"), {"ids": product_ids})
        await db.execute(text("DELETE FROM reviews WHERE product_id = ANY(:ids)"), {"ids": product_ids})
        await db.execute(sa_delete(ProductImage).where(ProductImage.product_id.in_(product_ids)))
        await db.execute(sa_delete(product_categories).where(product_categories.c.product_id.in_(product_ids)))
        await db.execute(sa_delete(Product).where(Product.catalog_id.in_(catalog_ids)))

    result = await db.execute(sa_delete(Catalog).where(Catalog.id.in_(catalog_ids)))
    await db.commit()
    return result.rowcount


async def delete_all(db: AsyncSession) -> int:
    await db.execute(text("DELETE FROM videos"))
    await db.execute(text("DELETE FROM reviews"))
    await db.execute(sa_delete(ProductImage))
    await db.execute(sa_delete(product_categories))
    await db.execute(sa_delete(Product))
    result = await db.execute(sa_delete(Catalog))
    await db.commit()
    return result.rowcount