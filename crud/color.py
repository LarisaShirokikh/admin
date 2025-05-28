# app/crud/color.py
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.color import Color
from app.schemas.color import ColorCreate, ColorUpdate

async def create_color(db: AsyncSession, color: ColorCreate) -> Color:
    """Создание нового цвета"""
    db_color = Color(
        name=color.name,
        code=color.code,
        is_active=color.is_active
    )
    
    db.add(db_color)
    await db.commit()
    await db.refresh(db_color)
    return db_color

async def get_color(db: AsyncSession, color_id: int) -> Optional[Color]:
    """Получение цвета по ID"""
    result = await db.execute(select(Color).where(Color.id == color_id))
    return result.scalar_one_or_none()

async def get_colors(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[Color]:
    """Получение списка цветов"""
    result = await db.execute(select(Color).offset(skip).limit(limit))
    return result.scalars().all()

async def update_color(db: AsyncSession, color_id: int, color: ColorUpdate) -> Optional[Color]:
    """Обновление цвета"""
    db_color = await get_color(db, color_id)
    if not db_color:
        return None
    
    # Обновляем только переданные поля
    update_data = color.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_color, key, value)
    
    await db.commit()
    await db.refresh(db_color)
    return db_color

async def delete_color(db: AsyncSession, color_id: int) -> bool:
    """Удаление цвета"""
    db_color = await get_color(db, color_id)
    if not db_color:
        return False
    
    await db.delete(db_color)
    await db.commit()
    return True