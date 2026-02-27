# app/api/v1/sitemap/router.py

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.dependencies import get_db
from app.models.product import Product
from app.models.catalog import Catalog
from app.models.category import Category
from app.models.brand import Brand

router = APIRouter()


def safe_isoformat(dt):
    """Безопасное преобразование datetime в ISO строку"""
    if dt is None:
        return None
    try:
        return dt.isoformat()
    except Exception:
        return None


@router.get("/slugs/")
async def get_all_slugs(db: AsyncSession = Depends(get_db)):
    """
    Все slug-и для генерации sitemap.xml на фронтенде.
    Один запрос вместо четырёх — быстрее и проще.
    """
    try:
        # Продукты
        products_result = await db.execute(
            select(Product.slug, Product.updated_at)
            .where(Product.is_active == True)
        )
        products = [
            {"slug": row[0], "updated_at": safe_isoformat(row[1])}
            for row in products_result.fetchall()
        ]

        # Каталоги
        catalogs_result = await db.execute(
            select(Catalog.slug, Catalog.updated_at)
            .where(Catalog.is_active == True)
        )
        catalogs = [
            {"slug": row[0], "updated_at": safe_isoformat(row[1])}
            for row in catalogs_result.fetchall()
        ]

        # Категории
        try:
            categories_result = await db.execute(
                select(Category.slug, Category.updated_at)
                .where(Category.is_active == True)
            )
        except Exception:
            categories_result = await db.execute(
                select(Category.slug)
                .where(Category.is_active == True)
            )
        categories = []
        for row in categories_result.fetchall():
            slug = row[0]
            updated_at = safe_isoformat(row[1]) if len(row) > 1 else None
            categories.append({"slug": slug, "updated_at": updated_at})

        # Бренды
        try:
            brands_result = await db.execute(
                select(Brand.slug, Brand.updated_at)
                .where(Brand.is_active == True)
            )
        except Exception:
            brands_result = await db.execute(
                select(Brand.slug)
                .where(Brand.is_active == True)
            )
        brands = []
        for row in brands_result.fetchall():
            slug = row[0]
            updated_at = safe_isoformat(row[1]) if len(row) > 1 else None
            brands.append({"slug": slug, "updated_at": updated_at})

        # Посты (блог)
        posts = []
        try:
            from app.models.posts import Post as PostModel
            posts_result = await db.execute(
                select(PostModel.slug, PostModel.updated_at)
                .where(PostModel.is_published == True)
            )
            posts = [
                {"slug": row[0], "updated_at": safe_isoformat(row[1])}
                for row in posts_result.fetchall()
            ]
        except Exception as e:
            logging.warning(f"Не удалось загрузить slug-и постов: {e}")

        return {
            "products": products,
            "catalogs": catalogs,
            "categories": categories,
            "brands": brands,
            "posts": posts,
            "total": len(products) + len(catalogs) + len(categories) + len(brands) + len(posts),
        }

    except Exception as e:
        logging.error(f"Ошибка при получении slug-ов для sitemap: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")