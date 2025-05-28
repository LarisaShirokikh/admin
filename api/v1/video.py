from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.crud.video import detect_product_for_video
from app.schemas.video import VideoUpdate
from app.models.video import Video
from app.models.product import Product
from app.models.category import Category
from app.models.catalog import Catalog
from app.deps import get_db
import os

router = APIRouter()

@router.post("/", response_model=VideoUpdate)
async def upload_product_video(
    title: str = Form(...),
    description: str = Form(None),
    auto_detect_product: bool = Form(True),  # По умолчанию True - всегда определяем продукт
    is_featured: bool = Form(False),
    video: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    # Сохраняем видео
    upload_dir = "media/videos"
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, video.filename)
    with open(file_path, "wb") as f:
        f.write(await video.read())
    
    # Переменные для привязки к продукту
    product_id = None
    product_slug_value = None
    
    # Автоопределение продукта, если включено
    if auto_detect_product:
        detected_product = await detect_product_for_video(db, title, description)
        
        if detected_product:
            product_id = detected_product.id
            product_slug_value = detected_product.slug
    
    # Создание записи в БД
    video_obj = Video(
        title=title,
        description=description,
        url=f"/media/videos/{video.filename}",
        product_id=product_id,
        product_slug=product_slug_value,
        is_featured=is_featured,
        auto_detected=auto_detect_product and product_id is not None
    )
    
    db.add(video_obj)
    await db.commit()
    await db.refresh(video_obj)
    
    # Запускаем асинхронную задачу для обработки видео (если используется Celery)
    # process_uploaded_video.delay(video_obj.id)
    
    return video_obj