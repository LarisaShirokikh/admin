from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.category import Category
from app.schemas.category import CategoryCreate

async def create_category(db: AsyncSession, data: dict):
    print("🔥 CREATE CATEGORY:", data)
    obj = Category(**data)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

async def get_categories(db: AsyncSession):
    result = await db.execute(select(Category))
    return result.scalars().all()