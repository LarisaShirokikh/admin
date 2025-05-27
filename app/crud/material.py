# app/crud/material.py
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.material import Material
from app.schemas.material import MaterialCreate, MaterialUpdate

async def create_material(db: AsyncSession, material: MaterialCreate) -> Material:
    """Создание нового материала"""
    db_material = Material(
        name=material.name,
        description=material.description,
        is_active=material.is_active
    )
    
    db.add(db_material)
    await db.commit()
    await db.refresh(db_material)
    return db_material

async def get_material(db: AsyncSession, material_id: int) -> Optional[Material]:
    """Получение материала по ID"""
    result = await db.execute(select(Material).where(Material.id == material_id))
    return result.scalar_one_or_none()

async def get_materials(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[Material]:
    """Получение списка материалов"""
    result = await db.execute(select(Material).offset(skip).limit(limit))
    return result.scalars().all()

async def update_material(db: AsyncSession, material_id: int, material: MaterialUpdate) -> Optional[Material]:
    """Обновление материала"""
    db_material = await get_material(db, material_id)
    if not db_material:
        return None
    
    # Обновляем только переданные поля
    update_data = material.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_material, key, value)
    
    await db.commit()
    await db.refresh(db_material)
    return db_material

async def delete_material(db: AsyncSession, material_id: int) -> bool:
    """Удаление материала"""
    db_material = await get_material(db, material_id)
    if not db_material:
        return False
    
    await db.delete(db_material)
    await db.commit()
    return True
