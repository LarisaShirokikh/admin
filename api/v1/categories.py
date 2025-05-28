import os
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.schemas.category import CategoryCreate, CategoryBase
from app.crud.category import create_category, get_categories
from app.deps import get_db

router = APIRouter()

@router.get("/", response_model=List[CategoryBase])
async def list_categories(db: AsyncSession = Depends(get_db)):
    return await get_categories(db)

@router.post("/", response_model=CategoryBase)
async def create_cat(
    name: str = Form(...),
    manufacturer_id: int = Form(...),
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    upload_dir = "media/categories"
    os.makedirs(upload_dir, exist_ok=True)
    
    # Путь к файлу
    file_location = os.path.join(upload_dir, image.filename)

    # Сохраняем файл
    with open(file_location, "wb") as f:
        f.write(await image.read())

    # создаем запись
    data = {
        "name": name,
        "manufacturer_id": manufacturer_id,
        "image_url": f"/media/categories/{image.filename}"
    }

    return await create_category(db, data)