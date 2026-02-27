import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from fastapi import UploadFile
from sqlalchemy import and_, delete as sa_delete, func, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import raise_400, raise_500
from app.models.category import Category
from app.models.product import Product
from app.schemas.category import CategoryDeleteResponse, CategoryStatusToggleResponse
from app.utils.text_utils import generate_seo_meta, generate_slug

logger = logging.getLogger(__name__)

CATEGORIES_DIR = f"{settings.UPLOAD_DIR}/categories"


# === File helpers ===

def _validate_image(image: UploadFile) -> str:
    if not image.filename:
        raise_400("No filename provided")
    ext = os.path.splitext(image.filename)[1].lower()
    if ext not in settings.ALLOWED_IMAGE_EXTENSIONS:
        raise_400(f"Unsupported file type. Allowed: {', '.join(settings.ALLOWED_IMAGE_EXTENSIONS)}")
    return ext


async def _save_image(image: UploadFile, ext: str) -> str:
    filename = f"{uuid.uuid4()}{ext}"
    os.makedirs(CATEGORIES_DIR, exist_ok=True)
    path = os.path.join(CATEGORIES_DIR, filename)

    content = await image.read()
    if not content:
        raise_400("Empty file")
    if len(content) > settings.MAX_IMAGE_SIZE:
        raise_400("File too large")

    with open(path, "wb") as f:
        f.write(content)
    return filename


def _delete_image(image_url: Optional[str]):
    if not image_url or not image_url.startswith("/media/categories/"):
        return
    path = os.path.join(CATEGORIES_DIR, os.path.basename(image_url))
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception as e:
            logger.warning("Failed to delete %s: %s", path, e)


# === CRUD ===

async def get_all(db: AsyncSession) -> List[Category]:
    result = await db.execute(select(Category).order_by(Category.name))
    return result.scalars().all()


async def get_by_id(db: AsyncSession, category_id: int) -> Optional[Category]:
    result = await db.execute(select(Category).where(Category.id == category_id))
    return result.scalar_one_or_none()


async def get_by_slug(db: AsyncSession, slug: str) -> Optional[Category]:
    result = await db.execute(select(Category).where(Category.slug == slug))
    return result.scalar_one_or_none()


async def get_with_products(db: AsyncSession, category_id: int) -> Optional[dict]:
    category = await get_by_id(db, category_id)
    if not category:
        return None
    products = await _get_products(db, category_id)
    return {"category": category, "products_count": len(products), "products": products}


async def create(
    db: AsyncSession,
    *,
    name: str,
    description: Optional[str],
    is_active: bool,
    image: UploadFile,
) -> Category:
    ext = _validate_image(image)
    filename = await _save_image(image, ext)

    try:
        slug = generate_slug(name.strip())
        seo = generate_seo_meta(name.strip())

        category = Category(
            name=name.strip(),
            slug=slug,
            description=description.strip() if description else f"Category: {name.strip()}",
            image_url=f"/media/categories/{filename}",
            is_active=is_active,
            meta_title=seo["meta_title"],
            meta_description=seo["meta_description"],
            meta_keywords=seo["meta_keywords"],
            product_count=0,
        )
        db.add(category)
        await db.commit()
        await db.refresh(category)
        return category

    except Exception as e:
        _delete_image(f"/media/categories/{filename}")
        raise_500(f"Failed to create category: {e}")


async def update(
    db: AsyncSession,
    category_id: int,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    is_active: Optional[bool] = None,
    image: Optional[UploadFile] = None,
) -> Optional[Category]:
    category = await get_by_id(db, category_id)
    if not category:
        return None

    data: Dict[str, Any] = {}
    old_image = category.image_url
    new_filename = None

    try:
        if image and image.filename:
            ext = _validate_image(image)
            new_filename = await _save_image(image, ext)
            data["image_url"] = f"/media/categories/{new_filename}"

        if name is not None:
            data["name"] = name.strip()
            data["slug"] = generate_slug(name.strip())
            data.update(generate_seo_meta(name.strip()))

        if description is not None:
            data["description"] = description.strip()

        if is_active is not None:
            data["is_active"] = is_active

        if data:
            await db.execute(update_stmt(category_id, data))
            await db.commit()

        if new_filename and old_image:
            _delete_image(old_image)

        return await get_by_id(db, category_id)

    except Exception as e:
        if new_filename:
            _delete_image(f"/media/categories/{new_filename}")
        raise_500(f"Failed to update category: {e}")


async def toggle_status(db: AsyncSession, category_id: int) -> Optional[CategoryStatusToggleResponse]:
    category = await get_by_id(db, category_id)
    if not category:
        return None

    new_status = not category.is_active
    await db.execute(update_stmt(category_id, {"is_active": new_status}))
    await db.commit()

    updated = await get_by_id(db, category_id)
    return CategoryStatusToggleResponse(
        message=f"Status changed to {'active' if new_status else 'inactive'}",
        category=updated,
    )


async def remove(
    db: AsyncSession, category_id: int, *, delete_products: bool = False
) -> Optional[CategoryDeleteResponse]:
    category = await get_by_id(db, category_id)
    if not category:
        return None

    products = await _get_products(db, category_id)

    if products:
        if delete_products:
            await db.execute(sa_delete(Product).where(Product.category_id == category_id))
        else:
            for p in products:
                p.category_id = None
            await db.flush()

    await db.execute(sa_delete(Category).where(Category.id == category_id))
    await db.commit()

    _delete_image(category.image_url)

    return CategoryDeleteResponse(
        message=f"Category '{category.name}' deleted",
        products_affected=len(products),
        products_deleted=len(products) if delete_products else 0,
        products_unlinked=len(products) if not delete_products else 0,
    )


async def get_stats(db: AsyncSession) -> dict:
    all_cats = await get_all(db)
    total = len(all_cats)
    active = sum(1 for c in all_cats if c.is_active)

    with_products = 0
    total_products = 0
    for cat in all_cats:
        products = await _get_products(db, cat.id)
        if products:
            with_products += 1
            total_products += len(products)

    return {
        "total_categories": total,
        "active_categories": active,
        "inactive_categories": total - active,
        "categories_with_products": with_products,
        "empty_categories": total - with_products,
        "total_products_in_categories": total_products,
        "average_products_per_category": round(total_products / total, 2) if total else 0,
    }


# === Internal helpers ===

async def _get_products(db: AsyncSession, category_id: int) -> List[Product]:
    result = await db.execute(
        select(Product).where(Product.category_id == category_id).order_by(Product.name)
    )
    return result.scalars().all()


def update_stmt(category_id: int, data: dict):
    return sa_update(Category).where(Category.id == category_id).values(**data)


# === Used by other modules ===

async def get_categories_with_products(db: AsyncSession) -> List[Category]:
    result = await db.execute(
        select(Category, func.count(Product.id).label("cnt"))
        .outerjoin(Product, and_(Product.category_id == Category.id, Product.is_active == True))
        .group_by(Category.id)
        .order_by(Category.name)
    )
    categories = []
    for cat, count in result.all():
        cat.product_count = count
        categories.append(cat)
    return categories


async def check_slug_exists(
        db: AsyncSession,
        slug: str,
        exclude_id: Optional[int] = None
) -> bool:
    filters = [Category.slug == slug]
    if exclude_id:
        filters.append(Category.id != exclude_id)
    result = await db.execute(select(Category).where(and_(*filters)))
    return result.scalar_one_or_none() is not None