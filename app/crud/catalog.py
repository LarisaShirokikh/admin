from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.catalog import Catalog
from app.schemas.catalog import CatalogCreate

async def create_catalog(db: AsyncSession, data: CatalogCreate):
    obj = Catalog(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

async def get_catalogs(db: AsyncSession):
    result = await db.execute(select(Catalog))
    return result.scalars().all()