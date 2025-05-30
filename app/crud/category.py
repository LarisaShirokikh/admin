# app/crud/category.py
import os
from typing import Any, Dict, List, Optional
import uuid

from fastapi import HTTPException, UploadFile
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, func, select, update
from app.models.category import Category
from app.models.product import Product

UPLOAD_DIR = "/app/media/categories"
ALLOWED_EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif", ".webp"]
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# === ФУНКЦИИ РАБОТЫ С ФАЙЛАМИ ===

def validate_image_file(image: UploadFile) -> str:
    """Валидация загружаемого изображения"""
    if not image.filename:
        raise HTTPException(status_code=422, detail="Имя файла не указано")
    
    file_ext = os.path.splitext(image.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Неподдерживаемый тип файла. Разрешены: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    return file_ext

async def save_image_file(image: UploadFile, file_ext: str) -> str:
    """Сохранение файла изображения"""
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_location = os.path.join(UPLOAD_DIR, unique_filename)
    
    try:
        file_content = await image.read()
        
        if len(file_content) == 0:
            raise HTTPException(status_code=422, detail="Загружен пустой файл")
        
        if len(file_content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=422, detail="Файл слишком большой")
        
        with open(file_location, "wb") as f:
            f.write(file_content)
        
        return unique_filename
    
    except HTTPException:
        if os.path.exists(file_location):
            os.remove(file_location)
        raise
    except Exception as e:
        if os.path.exists(file_location):
            os.remove(file_location)
        raise HTTPException(status_code=500, detail=f"Ошибка сохранения файла: {str(e)}")

def delete_image_file(image_url: str):
    """Удаление файла изображения"""
    if image_url and image_url.startswith("/media/categories/"):
        filename = os.path.basename(image_url)
        file_path = os.path.join(UPLOAD_DIR, filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Ошибка удаления файла {file_path}: {e}")

# === CRUD ФУНКЦИИ ===

async def create_category(db: AsyncSession, category_data: Dict[str, Any]) -> Category:
    """Создание новой категории"""
    category = Category(**category_data)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category

async def get_categories(db: AsyncSession) -> List[Category]:
    """Получение всех категорий"""
    result = await db.execute(
        select(Category).order_by(Category.name)
    )
    return result.scalars().all()

async def get_category_by_id(db: AsyncSession, category_id: int) -> Optional[Category]:
    """Получение категории по ID"""
    result = await db.execute(
        select(Category).where(Category.id == category_id)
    )
    return result.scalar_one_or_none()

async def get_category_by_slug(db: AsyncSession, slug: str) -> Optional[Category]:
    """Получение категории по slug"""
    result = await db.execute(
        select(Category).where(Category.slug == slug)
    )
    return result.scalar_one_or_none()

async def update_category(db: AsyncSession, category_id: int, update_data: Dict[str, Any]) -> Category:
    """Обновление категории"""
    await db.execute(
        update(Category)
        .where(Category.id == category_id)
        .values(**update_data)
    )
    await db.commit()
    
    result = await db.execute(
        select(Category).where(Category.id == category_id)
    )
    return result.scalar_one()

async def delete_category(db: AsyncSession, category_id: int) -> bool:
    """Удаление категории"""
    result = await db.execute(
        delete(Category).where(Category.id == category_id)
    )
    await db.commit()
    return result.rowcount > 0

async def get_products_by_category_id(db: AsyncSession, category_id: int) -> List[Product]:
    """Получение всех товаров в категории"""
    result = await db.execute(
        select(Product)
        .where(Product.category_id == category_id)
        .order_by(Product.name)
    )
    return result.scalars().all()

async def update_category_product_count(db: AsyncSession, category_id: int):
    """Обновление счетчика товаров в категории"""
    result = await db.execute(
        select(func.count(Product.id))
        .where(
            and_(
                Product.category_id == category_id,
                Product.is_active == True
            )
        )
    )
    product_count = result.scalar()
    
    await db.execute(
        update(Category)
        .where(Category.id == category_id)
        .values(product_count=product_count)
    )
    await db.commit()

async def get_categories_with_products(db: AsyncSession) -> List[Category]:
    """Получение категорий с количеством товаров"""
    result = await db.execute(
        select(
            Category,
            func.count(Product.id).label('product_count')
        )
        .outerjoin(Product, and_(
            Product.category_id == Category.id,
            Product.is_active == True
        ))
        .group_by(Category.id)
        .order_by(Category.name)
    )
    
    categories = []
    for category, count in result.all():
        category.product_count = count
        categories.append(category)
    
    return categories

async def search_categories(
    db: AsyncSession, 
    query: str,
    is_active: Optional[bool] = None
) -> List[Category]:
    """Поиск категорий по названию"""
    filters = [Category.name.ilike(f'%{query}%')]
    
    if is_active is not None:
        filters.append(Category.is_active == is_active)
    
    result = await db.execute(
        select(Category)
        .where(and_(*filters))
        .order_by(Category.name)
    )
    return result.scalars().all()

async def check_category_slug_exists(db: AsyncSession, slug: str, exclude_id: Optional[int] = None) -> bool:
    """Проверка существования slug"""
    filters = [Category.slug == slug]
    
    if exclude_id:
        filters.append(Category.id != exclude_id)
    
    result = await db.execute(
        select(Category).where(and_(*filters))
    )
    return result.scalar_one_or_none() is not None