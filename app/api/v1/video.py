# app/routers/video.py
import tempfile
import os
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks, Query, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.crud.video import (
    VideoProcessor, create_video, get_video_by_id, get_video_by_uuid,
    get_videos, get_videos_by_product_id, search_videos, suggest_products_for_video, update_video,
    delete_video, toggle_video_status, toggle_featured_status,
    auto_link_video_to_product, get_featured_videos, find_product_by_title
)
from app.schemas.video import VideoCreate, VideoUpdate, VideoResponse

router = APIRouter()

# Инициализируем процессор видео
video_processor = VideoProcessor(media_root="/app/media")

@router.post("/upload/", response_model=VideoResponse)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(""),
    product_title: Optional[str] = Form(None),  # Для поиска продукта по названию
    is_featured: bool = Form(False),
    db: AsyncSession = Depends(get_db)
):
    """Загрузка и обработка видео"""
    # Проверяем формат файла
    allowed_formats = ['.mp4', '.mov', '.avi', '.mkv', '.webm']
    file_extension = os.path.splitext(file.filename)[1].lower()
    
    if file_extension not in allowed_formats:
        raise HTTPException(400, f"Неподдерживаемый формат файла. Разрешены: {', '.join(allowed_formats)}")
    
    # Проверяем размер файла (макс 100MB)
    max_size = 100 * 1024 * 1024  # 100MB
    file_content = await file.read()
    if len(file_content) > max_size:
        raise HTTPException(400, "Файл слишком большой. Максимальный размер: 100MB")
    
    # Сохраняем во временный файл
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
        temp_file.write(file_content)
        temp_path = temp_file.name
    
    try:
        # Обрабатываем видео
        processing_result = video_processor.process_video(temp_path, file.filename)
        
        # Ищем продукт для привязки
        product_id = None
        if product_title:
            product = await find_product_by_title(db, product_title)
            if product:
                product_id = product.id
        
        # Создаем запись в базе данных
        video_data = VideoCreate(
            title=title,
            description=description,
            url=processing_result["video_path"],
            thumbnail_url=processing_result["thumbnail_path"],
            duration=processing_result["duration"],
            product_id=product_id,
            is_active=True,
            is_featured=is_featured
        )
        
        video = await create_video(db, video_data)
        
        # Если продукт не найден, пытаемся автоматически привязать по названию видео
        if not product_id:
            video = await auto_link_video_to_product(db, video.id)
        
        return video
        
    except Exception as e:
        raise HTTPException(500, f"Ошибка обработки видео: {str(e)}")
    
    finally:
        # Удаляем временный файл
        if os.path.exists(temp_path):
            os.unlink(temp_path)

@router.get("/", response_model=List[VideoResponse])
async def list_videos(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=1000),
    is_active: Optional[bool] = Query(None),
    is_featured: Optional[bool] = Query(None),
    product_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Получение списка видео с фильтрами"""
    return await get_videos(
        db, skip=skip, limit=limit, 
        is_active=is_active, is_featured=is_featured, 
        product_id=product_id
    )

@router.get("/featured/", response_model=List[VideoResponse])
async def list_featured_videos(
    limit: int = Query(10, le=50),
    db: AsyncSession = Depends(get_db)
):
    """Получение избранных видео"""
    return await get_featured_videos(db, limit=limit)

@router.get("/search/", response_model=List[VideoResponse])
async def search_videos_endpoint(
    q: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_db)
):
    """Поиск видео по названию"""
    return await search_videos(db, q)

@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Получение видео по ID"""
    video = await get_video_by_id(db, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    return video

@router.get("/uuid/{video_uuid}", response_model=VideoResponse)
async def get_video_by_uuid_endpoint(
    video_uuid: str,
    db: AsyncSession = Depends(get_db)
):
    """Получение видео по UUID"""
    video = await get_video_by_uuid(db, video_uuid)
    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    return video

@router.put("/{video_id}", response_model=VideoResponse)
async def update_video_endpoint(
    video_id: int,
    video_data: VideoUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Обновление видео"""
    video = await get_video_by_id(db, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    
    updated_video = await update_video(db, video_id, video_data)
    return updated_video

@router.delete("/{video_id}")
async def delete_video_endpoint(
    video_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Удаление видео"""
    video = await get_video_by_id(db, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    
    success = await delete_video(db, video_id)
    if success:
        return {"message": f"Видео '{video.title}' успешно удалено"}
    else:
        raise HTTPException(status_code=500, detail="Ошибка удаления видео")

@router.post("/{video_id}/toggle-status", response_model=VideoResponse)
async def toggle_video_status_endpoint(
    video_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Переключение статуса активности видео"""
    video = await get_video_by_id(db, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    
    updated_video = await toggle_video_status(db, video_id)
    return updated_video

@router.post("/{video_id}/toggle-featured", response_model=VideoResponse)
async def toggle_featured_status_endpoint(
    video_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Переключение статуса избранного видео"""
    video = await get_video_by_id(db, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    
    updated_video = await toggle_featured_status(db, video_id)
    return updated_video

@router.post("/{video_id}/auto-link-product", response_model=VideoResponse)
async def auto_link_product_endpoint(
    video_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Автоматическая привязка видео к продукту по названию"""
    video = await get_video_by_id(db, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    
    updated_video = await auto_link_video_to_product(db, video_id)
    return updated_video

@router.get("/product/{product_id}", response_model=List[VideoResponse])
async def get_product_videos(
    product_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Получение всех видео для продукта"""
    return await get_videos_by_product_id(db, product_id)

# Добавьте эндпоинт в роутер для предложений:
@router.get("/{video_id}/suggest-products")
async def suggest_products_for_video_endpoint(
    video_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Предложение продуктов для привязки к видео"""
    video = await get_video_by_id(db, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    
    suggestions = await suggest_products_for_video(db, video.title)
    
    return {
        "video_id": video_id,
        "video_title": video.title,
        "suggestions": [
            {
                "product_id": product.id,
                "product_name": product.name,
                "similarity_score": round(score * 100, 1)
            }
            for product, score in suggestions
        ]
    }