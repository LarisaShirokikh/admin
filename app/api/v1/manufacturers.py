from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.schemas.manufacturer import ManufacturerRead, ManufacturerCreate
from app.crud.manufacturer import create_manufacturer, get_manufacturers
from app.deps import get_db

router = APIRouter()

@router.get("/", response_model=List[ManufacturerRead])
async def list_manufacturers(db: AsyncSession = Depends(get_db)):
    return await get_manufacturers(db)

@router.post("/", response_model=ManufacturerRead)
async def create_man(db: AsyncSession = Depends(get_db), data: ManufacturerCreate = Depends()):
    return await create_manufacturer(db, data)