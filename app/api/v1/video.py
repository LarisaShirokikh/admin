# app/routers/video.py
import tempfile
import os
import logging
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

logger = logging.getLogger(__name__)
router = APIRouter()

# Инициализируем процессор видео
video_processor = VideoProcessor(media_root="/app/media")

@router.post("/upload/", response_model=VideoResponse)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(""),
    product_title: Optional[str] = Form(None),
    is_featured: bool = Form(False),
    db: AsyncSession = Depends(get_db)
):
    """Загрузка и обработка видео"""
    logger.info(f"🎬 Начинаем загрузку видео: {file.filename}, размер: {file.size if hasattr(file, 'size') else 'неизвестно'}")
    
    try:
        # Проверяем формат файла
        allowed_formats = ['.mp4', '.mov', '.avi', '.mkv', '.webm']
        file_extension = os.path.splitext(file.filename)[1].lower()
        
        if file_extension not in allowed_formats:
            logger.error(f"❌ Неподдерживаемый формат: {file_extension}")
            raise HTTPException(400, f"Неподдерживаемый формат файла. Разрешены: {', '.join(allowed_formats)}")
        
        logger.info(f"✅ Формат файла проверен: {file_extension}")
        
        # Проверяем права доступа к директории media
        media_dir = "/app/media"
        if not os.path.exists(media_dir):
            logger.error(f"❌ Директория {media_dir} не существует")
            raise HTTPException(500, f"Директория {media_dir} не найдена")
        
        if not os.access(media_dir, os.W_OK):
            logger.error(f"❌ Нет прав записи в директорию {media_dir}")
            raise HTTPException(500, f"Нет прав записи в директорию {media_dir}")
        
        logger.info(f"✅ Права доступа к {media_dir} проверены")
        
        # Проверяем место на диске
        import shutil
        total, used, free = shutil.disk_usage(media_dir)
        free_mb = free // (1024*1024)
        logger.info(f"💾 Свободное место: {free_mb} MB")
        
        if free_mb < 500:  # Меньше 500MB
            logger.error(f"❌ Недостаточно места на диске: {free_mb} MB")
            raise HTTPException(500, "Недостаточно места на диске")
        
        # Читаем файл частями для контроля памяти
        logger.info("📖 Начинаем чтение файла...")
        file_content = b""
        max_size = 100 * 1024 * 1024  # 100MB
        chunk_size = 1024 * 1024  # 1MB chunks
        
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            file_content += chunk
            
            if len(file_content) > max_size:
                logger.error(f"❌ Файл слишком большой: {len(file_content)} байт")
                raise HTTPException(400, "Файл слишком большой. Максимальный размер: 100MB")
        
        logger.info(f"✅ Файл прочитан: {len(file_content)} байт")
        
        # Создаем временный файл
        logger.info("📁 Создаем временный файл...")
        temp_dir = tempfile.gettempdir()
        logger.info(f"📁 Временная директория: {temp_dir}")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension, dir=temp_dir) as temp_file:
            temp_file.write(file_content)
            temp_path = temp_file.name
        
        logger.info(f"✅ Временный файл создан: {temp_path}")
        
        try:
            # Проверяем, что файл действительно создался
            if not os.path.exists(temp_path):
                logger.error(f"❌ Временный файл не создался: {temp_path}")
                raise HTTPException(500, "Ошибка создания временного файла")
            
            temp_size = os.path.getsize(temp_path)
            logger.info(f"✅ Размер временного файла: {temp_size} байт")
            
            # Обрабатываем видео
            logger.info("🔄 Начинаем обработку видео...")
            processing_result = video_processor.process_video(temp_path, file.filename)
            logger.info(f"✅ Видео обработано: {processing_result}")
            
            # Ищем продукт для привязки
            product_id = None
            if product_title:
                logger.info(f"🔍 Ищем продукт: {product_title}")
                product = await find_product_by_title(db, product_title)
                if product:
                    product_id = product.id
                    logger.info(f"✅ Продукт найден: {product_id}")
                else:
                    logger.info("❌ Продукт не найден")
            
            # Создаем запись в базе данных
            logger.info("💾 Сохраняем в базу данных...")
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
            logger.info(f"✅ Видео сохранено в БД: ID {video.id}")
            
            # Если продукт не найден, пытаемся автоматически привязать
            if not product_id:
                logger.info("🔗 Пытаемся автоматически привязать к продукту...")
                video = await auto_link_video_to_product(db, video.id)
            
            logger.info(f"🎉 Загрузка видео завершена успешно: {video.id}")
            return video
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки видео: {str(e)}", exc_info=True)
            raise HTTPException(500, f"Ошибка обработки видео: {str(e)}")
        
        finally:
            # Удаляем временный файл
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                    logger.info(f"🗑️ Временный файл удален: {temp_path}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось удалить временный файл {temp_path}: {e}")
            
    except HTTPException:
        # Переиспользуем HTTP исключения как есть
        raise
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при загрузке видео: {str(e)}", exc_info=True)
        raise HTTPException(500, f"Неожиданная ошибка: {str(e)}")

# Добавим эндпоинт для проверки состояния системы
@router.get("/system-check")
async def video_system_check():
    """Проверка системы для загрузки видео"""
    try:
        checks = {}
        
        # Проверяем медиа директорию
        media_dir = "/app/media"
        checks["media_dir_exists"] = os.path.exists(media_dir)
        checks["media_dir_writable"] = os.access(media_dir, os.W_OK) if checks["media_dir_exists"] else False
        
        # Проверяем временную директорию
        temp_dir = tempfile.gettempdir()
        checks["temp_dir"] = temp_dir
        checks["temp_dir_writable"] = os.access(temp_dir, os.W_OK)
        
        # Проверяем место на диске
        if checks["media_dir_exists"]:
            import shutil
            total, used, free = shutil.disk_usage(media_dir)
            checks["disk_space_mb"] = free // (1024*1024)
        
        # Проверяем процессор видео
        try:
            video_processor_status = str(video_processor)
            checks["video_processor"] = "OK"
        except Exception as e:
            checks["video_processor"] = f"Error: {str(e)}"
        
        return {
            "status": "OK" if all([
                checks.get("media_dir_exists", False),
                checks.get("media_dir_writable", False),
                checks.get("temp_dir_writable", False),
                checks.get("disk_space_mb", 0) > 100
            ]) else "ERROR",
            "checks": checks
        }
        
    except Exception as e:
        return {
            "status": "ERROR",
            "error": str(e)
        }

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