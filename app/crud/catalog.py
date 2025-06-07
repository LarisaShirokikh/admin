# app/crud/catalog.py (полная версия)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from typing import Optional, List
import re

from app.models.catalog import Catalog
from app.schemas.catalog import CatalogCreate, CatalogUpdate

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def generate_slug(name: str) -> str:
    """Генерация slug из названия"""
    # Преобразуем в нижний регистр и заменяем пробелы и спецсимволы на дефисы
    slug = re.sub(r'[^\w\s-]', '', name.lower())
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug.strip('-')

async def ensure_unique_slug(db: AsyncSession, slug: str, catalog_id: Optional[int] = None) -> str:
    """Обеспечение уникальности slug"""
    original_slug = slug
    counter = 1
    
    while True:
        # Проверяем существование slug
        query = select(Catalog).where(Catalog.slug == slug)
        if catalog_id:
            query = query.where(Catalog.id != catalog_id)
        
        result = await db.execute(query)
        existing = result.scalar_one_or_none()
        
        if not existing:
            return slug
        
        # Если slug занят, добавляем счетчик
        slug = f"{original_slug}-{counter}"
        counter += 1

# ========== ОСНОВНЫЕ CRUD ОПЕРАЦИИ ==========

async def create_catalog(db: AsyncSession, data: CatalogCreate) -> Catalog:
    """Создать новый каталог"""
    # Генерируем slug если не указан
    if not data.slug:
        slug = generate_slug(data.name)
    else:
        slug = data.slug
    
    # Обеспечиваем уникальность slug
    unique_slug = await ensure_unique_slug(db, slug)
    
    # Создаем объект каталога
    catalog_data = data.model_dump()
    catalog_data['slug'] = unique_slug
    
    obj = Catalog(**catalog_data)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

async def get_catalogs(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[Catalog]:
    """Получить список каталогов с пагинацией"""
    query = select(Catalog).offset(skip).limit(limit).order_by(Catalog.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()

async def get_catalog(db: AsyncSession, catalog_id: int) -> Optional[Catalog]:
    """Получить каталог по ID"""
    query = select(Catalog).where(Catalog.id == catalog_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def get_catalog_by_slug(db: AsyncSession, slug: str) -> Optional[Catalog]:
    """Получить каталог по slug"""
    query = select(Catalog).where(Catalog.slug == slug)
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def update_catalog(db: AsyncSession, catalog_id: int, data: CatalogUpdate) -> Optional[Catalog]:
    """Обновить каталог по ID"""
    # Получаем существующий каталог
    existing_catalog = await get_catalog(db, catalog_id)
    if not existing_catalog:
        return None
    
    # Подготавливаем данные для обновления
    update_data = data.model_dump(exclude_unset=True)
    
    # Обрабатываем slug если он изменился
    if 'slug' in update_data and update_data['slug']:
        unique_slug = await ensure_unique_slug(db, update_data['slug'], catalog_id)
        update_data['slug'] = unique_slug
    elif 'name' in update_data and not update_data.get('slug'):
        # Если изменилось имя но slug не указан, генерируем новый slug
        new_slug = generate_slug(update_data['name'])
        unique_slug = await ensure_unique_slug(db, new_slug, catalog_id)
        update_data['slug'] = unique_slug
    
    if update_data:
        # Выполняем обновление
        query = (
            update(Catalog)
            .where(Catalog.id == catalog_id)
            .values(**update_data)
            .returning(Catalog)
        )
        result = await db.execute(query)
        await db.commit()
        
        # Возвращаем обновленный объект
        updated_catalog = result.scalar_one_or_none()
        if updated_catalog:
            await db.refresh(updated_catalog)
        return updated_catalog
    
    return existing_catalog

async def delete_catalog(db: AsyncSession, catalog_id: int) -> bool:
    """Удалить каталог по ID"""
    # Проверяем существование каталога
    existing_catalog = await get_catalog(db, catalog_id)
    if not existing_catalog:
        return False
    
    # Удаляем каталог
    query = delete(Catalog).where(Catalog.id == catalog_id)
    result = await db.execute(query)
    await db.commit()
    
    return result.rowcount > 0

async def toggle_catalog_status(db: AsyncSession, catalog_id: int) -> Optional[Catalog]:
    """Переключить статус активности каталога"""
    catalog = await get_catalog(db, catalog_id)
    if not catalog:
        return None
    
    new_status = not catalog.is_active
    update_data = CatalogUpdate(is_active=new_status)
    
    return await update_catalog(db, catalog_id, update_data)

# ========== СТАТИСТИКА И ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ ==========

async def count_catalogs(db: AsyncSession) -> int:
    """Подсчитать общее количество каталогов"""
    query = select(func.count(Catalog.id))
    result = await db.execute(query)
    return result.scalar()

async def count_active_catalogs(db: AsyncSession) -> int:
    """Подсчитать активные каталоги"""
    query = select(func.count(Catalog.id)).where(Catalog.is_active == True)
    result = await db.execute(query)
    return result.scalar()

async def get_catalogs_by_category(db: AsyncSession, category_id: int, skip: int = 0, limit: int = 100) -> List[Catalog]:
    """Получить каталоги по категории"""
    query = (
        select(Catalog)
        .where(Catalog.category_id == category_id)
        .offset(skip)
        .limit(limit)
        .order_by(Catalog.created_at.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()

async def get_catalogs_by_brand(db: AsyncSession, brand_id: int, skip: int = 0, limit: int = 100) -> List[Catalog]:
    """Получить каталоги по бренду"""
    query = (
        select(Catalog)
        .where(Catalog.brand_id == brand_id)
        .offset(skip)
        .limit(limit)
        .order_by(Catalog.created_at.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()

async def search_catalogs(db: AsyncSession, search_term: str, skip: int = 0, limit: int = 100) -> List[Catalog]:
    """Поиск каталогов по названию или описанию"""
    query = (
        select(Catalog)
        .where(
            (Catalog.name.ilike(f"%{search_term}%")) |
            (Catalog.description.ilike(f"%{search_term}%"))
        )
        .offset(skip)
        .limit(limit)
        .order_by(Catalog.created_at.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()

async def get_active_catalogs(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[Catalog]:
    """Получить только активные каталоги"""
    query = (
        select(Catalog)
        .where(Catalog.is_active == True)
        .offset(skip)
        .limit(limit)
        .order_by(Catalog.created_at.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()