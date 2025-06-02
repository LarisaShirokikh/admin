# app/crud/brand.py
from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.models.brand import Brand
from app.schemas.brand import BrandCreate, BrandUpdate
import re

async def create_brand(db: AsyncSession, brand: BrandCreate) -> Brand:
    """Создание нового бренда"""
    # Автоматическая генерация slug если не указан
    slug = brand.slug
    if not slug:
        slug = generate_slug(brand.name)
        
        # Проверяем уникальность сгенерированного slug
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
        is_active=brand.is_active
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
    """Получение бренда по ID"""
    result = await db.execute(select(Brand).where(Brand.id == brand_id))
    return result.scalar_one_or_none()

async def get_brand_by_slug(db: AsyncSession, slug: str) -> Optional[Brand]:
    """Получение бренда по slug"""
    result = await db.execute(select(Brand).where(Brand.slug == slug))
    return result.scalar_one_or_none()

async def get_brands(
    db: AsyncSession, 
    skip: int = 0, 
    limit: int = 100,
    active_only: bool = False,
    search: Optional[str] = None
) -> List[Brand]:
    """Получение списка брендов с фильтрацией"""
    query = select(Brand)
    
    # Фильтр по активности
    if active_only:
        query = query.where(Brand.is_active == True)
    
    # Поиск по названию и описанию
    if search:
        search_filter = f"%{search}%"
        query = query.where(
            Brand.name.ilike(search_filter) | 
            Brand.description.ilike(search_filter)
        )
    
    # Сортировка и пагинация
    query = query.order_by(Brand.name).offset(skip).limit(limit)
    
    result = await db.execute(query)
    return list(result.scalars().all())

async def update_brand(db: AsyncSession, brand_id: int, brand: BrandUpdate) -> Optional[Brand]:
    """Обновление бренда"""
    db_brand = await get_brand(db, brand_id)
    if not db_brand:
        return None
    
    # Обновляем только переданные поля
    update_data = brand.model_dump(exclude_unset=True)
    
    # Обработка URL полей
    if 'logo_url' in update_data and update_data['logo_url']:
        update_data['logo_url'] = str(update_data['logo_url'])
    if 'website' in update_data and update_data['website']:
        update_data['website'] = str(update_data['website'])
    
    # Генерация slug из имени, если slug пустой но имя изменилось
    if 'name' in update_data and not update_data.get('slug'):
        new_slug = generate_slug(update_data['name'])
        if new_slug != db_brand.slug:
            # Проверяем уникальность
            counter = 1
            original_slug = new_slug
            while await get_brand_by_slug(db, new_slug) and new_slug != db_brand.slug:
                new_slug = f"{original_slug}-{counter}"
                counter += 1
            update_data['slug'] = new_slug
    
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
    """Удаление бренда"""
    db_brand = await get_brand(db, brand_id)
    if not db_brand:
        return False
    
    try:
        await db.delete(db_brand)
        await db.commit()
        return True
    except IntegrityError:
        await db.rollback()
        # Можно также сделать мягкое удаление, установив is_active = False
        db_brand.is_active = False
        await db.commit()
        return True

async def get_brands_count(db: AsyncSession, active_only: bool = False) -> int:
    """Подсчет общего количества брендов"""
    from sqlalchemy import func
    
    query = select(func.count(Brand.id))
    if active_only:
        query = query.where(Brand.is_active == True)
    
    result = await db.execute(query)
    return result.scalar()

async def check_brand_slug_exists(db: AsyncSession, slug: str, exclude_id: Optional[int] = None) -> bool:
    """Проверка существования slug"""
    query = select(Brand.id).where(Brand.slug == slug)
    if exclude_id:
        query = query.where(Brand.id != exclude_id)
    
    result = await db.execute(query)
    return result.scalar_one_or_none() is not None

def generate_slug(name: str) -> str:
    """Генерация slug из названия"""
    # Транслитерация русских букв (базовая)
    translit_map = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
    }
    
    slug = name.lower()
    
    # Транслитерация
    for ru, en in translit_map.items():
        slug = slug.replace(ru, en)
    
    # Оставляем только буквы, цифры и дефисы
    slug = re.sub(r'[^a-zA-Z0-9\-]', '-', slug)
    
    # Убираем множественные дефисы и дефисы в начале/конце
    slug = re.sub(r'-+', '-', slug).strip('-')
    
    return slug