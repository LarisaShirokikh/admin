import os
import uuid
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.schemas.category import CategoryCreate, CategoryBase
from app.crud.category import create_category, get_categories
from app.deps import get_db
from app.utils.text_utils import generate_seo_meta, generate_slug

router = APIRouter()

@router.get("/", response_model=List[CategoryBase])
async def list_categories(db: AsyncSession = Depends(get_db)):
    return await get_categories(db)

@router.post("/", response_model=CategoryBase)
async def create_cat(
    name: str = Form(...),
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Создание категории с обязательным изображением (PNG приоритетно)"""
    
    # Допустимые форматы
    allowed_extensions = [".png", ".jpg", ".jpeg", ".gif", ".webp"]
    max_file_size = 10 * 1024 * 1024  # 10MB
    
    # Проверка файла
    if not image.filename:
        raise HTTPException(status_code=422, detail="Имя файла не указано")
    
    file_ext = os.path.splitext(image.filename)[1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=422,
            detail=f"Неподдерживаемый тип файла. Разрешены: {', '.join(allowed_extensions)}"
        )
    
    # Генерация уникального имени файла
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    
    # Путь к директории
    upload_dir = "/var/www/media/categories"
    os.makedirs(upload_dir, exist_ok=True)
    
    file_location = os.path.join(upload_dir, unique_filename)
    
    try:
        # Сохранение файла
        file_content = await image.read()
        
        if len(file_content) == 0:
            raise HTTPException(status_code=422, detail="Загружен пустой файл")
        
        with open(file_location, "wb") as f:
            f.write(file_content)

        # Генерация slug из названия
        slug = generate_slug(name.strip())
        
        # Автоматическая генерация SEO мета-тегов
        seo_meta = generate_seo_meta(name.strip())
        
        # Создание записи в БД
        data = {
            "name": name.strip(),
            "slug": name.lower().replace(" ", "-"),
            "image_url": f"/media/categories/{unique_filename}",
            "description": f"Категория товаров: {name.strip()}",
            "is_active": True,
            "meta_title": seo_meta["meta_title"],
            "meta_description": seo_meta["meta_description"], 
            "meta_keywords": seo_meta["meta_keywords"],
            "product_count": 0

        }
        
        return await create_category(db, data)
        
    except HTTPException:
        # Удаление файла при ошибке валидации
        if os.path.exists(file_location):
            os.remove(file_location)
        raise
        
    except Exception as e:
        # Удаление файла при других ошибках
        if os.path.exists(file_location):
            os.remove(file_location)
        raise HTTPException(status_code=500, detail=f"Ошибка создания категории: {str(e)}")