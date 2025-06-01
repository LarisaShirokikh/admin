from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.crud.brand import create_brand, get_brands
from app.schemas.catalog import CatalogCreate, CatalogBase
from app.deps import get_db

router = APIRouter()

@router.get("/", response_model=List[CatalogBase])
async def list_catalogs(db: AsyncSession = Depends(get_db)):
    return await get_brands(db)

@router.post("/", response_model=CatalogBase)
async def create_cat(db: AsyncSession = Depends(get_db), data: CatalogCreate = Depends()):
    return await create_brand(db, data)