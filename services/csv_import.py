import pandas as pd
import json
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Category, Catalog
from app.models.brand import Brand
from app.schemas.product import ProductCreate
from app.schemas.product_image import ProductImageCreate
from app.crud.product import create_product


async def get_or_create_brand(db: AsyncSession, name: str) -> Brand:
    """Получение или создание бренда по имени"""
    result = await db.execute(select(Brand).where(Brand.name == name))
    brand = result.scalar_one_or_none()
    if not brand:
        # Создаем slug из имени бренда
        slug = re.sub(r'[^a-zA-Z0-9]', '-', name.lower())
        slug = re.sub(r'-+', '-', slug).strip('-')
        
        brand = Brand(name=name, slug=slug)
        db.add(brand)
        await db.flush()
    return brand


async def get_or_create_category(db: AsyncSession, name: str, brand_id: int) -> Category:
    """Получение или создание категории по имени и ID бренда"""
    result = await db.execute(
        select(Category).where(Category.name == name, Category.brand_id == brand_id)
    )
    category = result.scalar_one_or_none()
    if not category:
        # Создаем slug из имени категории
        slug = re.sub(r'[^a-zA-Z0-9]', '-', name.lower())
        slug = re.sub(r'-+', '-', slug).strip('-')
        
        category = Category(name=name, brand_id=brand_id, slug=slug)
        db.add(category)
        await db.flush()
    return category


async def get_or_create_catalog(db: AsyncSession, name: str, category_id: int) -> Catalog:
    """Получение или создание каталога по имени и ID категории"""
    result = await db.execute(
        select(Catalog).where(Catalog.name == name, Catalog.category_id == category_id)
    )
    catalog = result.scalar_one_or_none()
    if not catalog:
        # Создаем slug из имени каталога
        slug = re.sub(r'[^a-zA-Z0-9]', '-', name.lower())
        slug = re.sub(r'-+', '-', slug).strip('-')
        
        catalog = Catalog(name=name, category_id=category_id, slug=slug)
        db.add(catalog)
        await db.flush()
    return catalog


async def import_products_from_df(df: pd.DataFrame, db: AsyncSession):
    """Импорт продуктов из DataFrame"""
    for _, row in df.iterrows():
        try:
            # Получаем или создаем бренд вместо производителя
            brand = await get_or_create_brand(db, row["manufacturer"])
            category = await get_or_create_category(db, row["category"], brand.id)
            catalog = await get_or_create_catalog(db, row["catalog"], category.id)

            # Обработка характеристик и изображений
            characteristics = json.loads(row.get("characteristics", "{}"))
            image_urls = json.loads(row.get("image_urls", "[]"))
            images = [ProductImageCreate(url=url, is_main=(i == 0)) for i, url in enumerate(image_urls)]

            # Создаем slug для продукта
            product_slug = re.sub(r'[^a-zA-Z0-9]', '-', row["name"].lower())
            product_slug = re.sub(r'-+', '-', product_slug).strip('-')

            # Создаем продукт
            product = ProductCreate(
                name=row["name"],
                description=row.get("description", ""),
                price=float(row["price"]),
                in_stock=bool(row["in_stock"]),
                catalog_name=row["catalog"],  # Изменено с catalog_id на catalog_name для совместимости с create_product
                characteristics=characteristics,
                images=images,
                slug=product_slug
            )
            
            # Создаем продукт в БД
            await create_product(db, product)

        except Exception as e:
            print(f"[ERROR] Ошибка в строке: {row.to_dict()} — {e}")
    
    # Фиксируем транзакцию
    await db.commit()