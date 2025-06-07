# app/routers/video.py (защищенная версия)
import tempfile
import os
import logging
from typing import List, Optional
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks, Query, Form, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.crud.video import (
    VideoProcessor, create_video, get_video_by_id, get_video_by_uuid,
    get_videos, get_videos_by_product_id, search_videos, suggest_products_for_video, update_video,
    delete_video, toggle_video_status, toggle_featured_status,
    auto_link_video_to_product, get_featured_videos, find_product_by_title
)
from app.schemas.video import VideoCreate, VideoUpdate, VideoResponse

# НОВЫЕ ИМПОРТЫ для защиты
from app.deps.admin_auth import get_current_active_admin, get_current_superuser, check_admin_rate_limit
from app.models.admin import AdminUser
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)
router = APIRouter()

# Инициализируем процессор видео
video_processor = VideoProcessor(media_root="/app/media")

# Глобальный счетчик загрузок видео (в продакшене лучше использовать Redis)
video_upload_stats = defaultdict(int)
MAX_UPLOADS_PER_USER_PER_HOUR = 5
MAX_UPLOADS_GLOBAL_PER_HOUR = 20

def check_upload_limits(current_user: AdminUser) -> None:
    """Проверка лимитов на загрузку видео"""
    user_uploads = video_upload_stats[current_user.username]
    total_uploads = sum(video_upload_stats.values())
    
    if user_uploads >= MAX_UPLOADS_PER_USER_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail=f"Превышен лимит загрузок на пользователя ({MAX_UPLOADS_PER_USER_PER_HOUR}/час). "
                   f"Попробуйте позже."
        )
    
    if total_uploads >= MAX_UPLOADS_GLOBAL_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail=f"Превышен глобальный лимит загрузок ({MAX_UPLOADS_GLOBAL_PER_HOUR}/час). "
                   f"Попробуйте позже."
        )

def register_upload(current_user: AdminUser) -> None:
    """Регистрация новой загрузки"""
    video_upload_stats[current_user.username] += 1
    print(f"UPLOAD_REGISTERED: by {current_user.username}. "
          f"User uploads: {video_upload_stats[current_user.username]}, "
          f"Total: {sum(video_upload_stats.values())}")

def validate_video_file(file: UploadFile) -> None:
    """Дополнительная валидация видео файла"""
    # Проверка расширения
    allowed_formats = ['.mp4', '.mov', '.avi', '.mkv', '.webm']
    file_extension = os.path.splitext(file.filename)[1].lower()
    if file_extension not in allowed_formats:
        raise HTTPException(400, f"Неподдерживаемый формат. Разрешены: {', '.join(allowed_formats)}")
    
    # Проверка Content-Type
    allowed_content_types = [
        'video/mp4', 'video/quicktime', 'video/x-msvideo', 
        'video/x-matroska', 'video/webm'
    ]
    if file.content_type and file.content_type not in allowed_content_types:
        raise HTTPException(400, f"Недопустимый Content-Type: {file.content_type}")
    
    # Проверка имени файла на подозрительные символы
    if any(char in file.filename for char in ['<', '>', ':', '"', '|', '?', '*', '\0']):
        raise HTTPException(400, "Недопустимые символы в имени файла")
    
    # Проверка длины имени файла
    if len(file.filename) > 100:
        raise HTTPException(400, "Слишком длинное имя файла (максимум 100 символов)")

# ========== ЗАГРУЗКА ВИДЕО (строгая защита) ==========

@router.post("/upload/", response_model=VideoResponse)
async def upload_video(
    request: Request,  # Добавляем Request
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(""),
    product_title: Optional[str] = Form(None),
    is_featured: bool = Form(False),
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """Загрузка видео - БЫСТРАЯ версия с максимальной защитой"""
    # ЭКСТРЕМАЛЬНО СТРОГИЙ rate limiting для загрузки
    check_admin_rate_limit(request, max_requests=3, window_minutes=30)
    
    # Проверяем лимиты загрузки
    check_upload_limits(current_user)
    
    # Дополнительная валидация файла
    validate_video_file(file)
    
    # Логируем начало загрузки
    print(f"VIDEO_UPLOAD_START: Admin {current_user.username} uploading '{file.filename}' with title '{title}'")
    
    logger.info(f"🎬 Загрузка видео: {file.filename} by {current_user.username}")
    
    # ПРЯМАЯ запись в финальное место без временных файлов
    file_uuid = str(uuid.uuid4())
    base_name = os.path.splitext(file.filename)[0]
    # Очищаем имя файла от опасных символов
    safe_base_name = "".join(c for c in base_name if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
    output_filename = f"{file_uuid}_{safe_base_name}.mp4"
    final_path = f"/app/media/videos/{output_filename}"
    
    try:
        # Создаем директорию если не существует
        os.makedirs("/app/media/videos", exist_ok=True)
        
        # ПОТОКОВАЯ запись напрямую в финальный файл
        total_size = 0
        max_size = 100 * 1024 * 1024  # 100MB
        
        with open(final_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)  # 1MB chunk
                if not chunk:
                    break
                
                total_size += len(chunk)
                if total_size > max_size:
                    # Удаляем файл если превышен размер
                    os.unlink(final_path)
                    raise HTTPException(400, "Файл слишком большой. Максимум: 100MB")
                
                f.write(chunk)
        
        # Устанавливаем права
        try:
            import subprocess
            subprocess.run(['chmod', '644', final_path], check=True)
            logger.info(f"🔧 Права установлены: {final_path}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось установить права: {e}")
        
        # Ищем продукт
        product_id = None
        if product_title:
            product = await find_product_by_title(db, product_title)
            if product:
                product_id = product.id
        
        # Сохраняем в БД
        video_data = VideoCreate(
            title=title,
            description=description,
            url=f"/media/videos/{output_filename}",
            thumbnail_url=None,
            duration=None,
            product_id=product_id,
            is_active=True,
            is_featured=is_featured
        )
        
        video = await create_video(db, video_data)
        
        # Автопривязка к продукту
        if not product_id:
            video = await auto_link_video_to_product(db, video.id)
        
        # Регистрируем загрузку
        register_upload(current_user)
        
        print(f"VIDEO_UPLOAD_SUCCESS: Video ID {video.id} uploaded by {current_user.username}")
        logger.info(f"✅ Видео загружено: ID {video.id} by {current_user.username}")
        
        return video
        
    except HTTPException:
        # Удаляем файл при ошибке
        if os.path.exists(final_path):
            os.unlink(final_path)
        raise
    except Exception as e:
        # Удаляем файл при ошибке
        if os.path.exists(final_path):
            os.unlink(final_path)
        print(f"VIDEO_UPLOAD_ERROR: Failed upload by {current_user.username}: {str(e)}")
        logger.error(f"❌ Ошибка загрузки: {str(e)}")
        raise HTTPException(500, f"Ошибка загрузки: {str(e)}")

# ========== СИСТЕМНЫЕ ПРОВЕРКИ (для всех админов) ==========

@router.get("/system-check")
async def video_system_check(
    request: Request,
    current_user: AdminUser = Depends(get_current_active_admin)  # ЗАЩИТА
):
    """Проверка системы для загрузки видео"""
    check_admin_rate_limit(request, max_requests=10, window_minutes=1)
    
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
        
        # Добавляем статистику загрузок
        checks["upload_stats"] = {
            "user_uploads_this_hour": video_upload_stats[current_user.username],
            "total_uploads_this_hour": sum(video_upload_stats.values()),
            "user_limit": MAX_UPLOADS_PER_USER_PER_HOUR,
            "global_limit": MAX_UPLOADS_GLOBAL_PER_HOUR
        }
        
        print(f"Admin {current_user.username} checked video system status")
        
        return {
            "status": "OK" if all([
                checks.get("media_dir_exists", False),
                checks.get("media_dir_writable", False),
                checks.get("temp_dir_writable", False),
                checks.get("disk_space_mb", 0) > 100
            ]) else "ERROR",
            "checks": checks,
            "requested_by": current_user.username,
            "timestamp": datetime.utcnow()
        }
        
    except Exception as e:
        print(f"ERROR: Video system check failed for {current_user.username}: {str(e)}")
        return {
            "status": "ERROR",
            "error": str(e),
            "requested_by": current_user.username
        }

# ========== ЧТЕНИЕ (для всех админов) ==========

@router.get("/", response_model=List[VideoResponse])
async def list_videos(
    request: Request,  # Добавляем Request
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=1000),
    is_active: Optional[bool] = Query(None),
    is_featured: Optional[bool] = Query(None),
    product_id: Optional[int] = Query(None),
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """Получение списка видео с фильтрами"""
    check_admin_rate_limit(request, max_requests=100, window_minutes=1)
    
    print(f"Admin {current_user.username} accessing videos list")
    
    videos = await get_videos(
        db, skip=skip, limit=limit, 
        is_active=is_active, is_featured=is_featured, 
        product_id=product_id
    )
    return videos

@router.get("/stats/summary")
async def get_videos_stats(
    request: Request,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Статистика по видео
    """
    check_admin_rate_limit(request, max_requests=20, window_minutes=1)
    
    # Получаем базовую статистику
    all_videos = await get_videos(db, skip=0, limit=10000)
    featured_videos = await get_featured_videos(db, limit=1000)
    
    total_videos = len(all_videos)
    active_videos = len([v for v in all_videos if v.is_active])
    inactive_videos = total_videos - active_videos
    featured_count = len(featured_videos)
    
    # Видео с привязкой к продуктам
    with_products = len([v for v in all_videos if v.product_id])
    without_products = total_videos - with_products
    
    stats = {
        "total_videos": total_videos,
        "active_videos": active_videos,
        "inactive_videos": inactive_videos,
        "featured_videos": featured_count,
        "videos_with_products": with_products,
        "videos_without_products": without_products,
        "upload_limits": {
            "user_uploads_this_hour": video_upload_stats[current_user.username],
            "total_uploads_this_hour": sum(video_upload_stats.values()),
            "user_limit": MAX_UPLOADS_PER_USER_PER_HOUR,
            "global_limit": MAX_UPLOADS_GLOBAL_PER_HOUR
        },
        "last_updated": datetime.utcnow(),
        "requested_by": current_user.username,
        "user_role": "superuser" if current_user.is_superuser else "admin"
    }
    
    print(f"Admin {current_user.username} requested videos statistics")
    return stats

@router.get("/featured/", response_model=List[VideoResponse])
async def list_featured_videos(
    request: Request,  # Добавляем Request
    limit: int = Query(10, le=50),
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """Получение избранных видео"""
    check_admin_rate_limit(request)
    
    videos = await get_featured_videos(db, limit=limit)
    return videos

@router.get("/search/", response_model=List[VideoResponse])
async def search_videos_endpoint(
    request: Request,  # Добавляем Request
    q: str = Query(..., min_length=2),
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """Поиск видео по названию"""
    check_admin_rate_limit(request)
    
    videos = await search_videos(db, q)
    return videos

@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(
    request: Request,  # Добавляем Request
    video_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """Получение видео по ID"""
    check_admin_rate_limit(request)
    
    video = await get_video_by_id(db, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    
    print(f"Admin {current_user.username} viewed video {video_id}")
    return video

@router.get("/uuid/{video_uuid}", response_model=VideoResponse)
async def get_video_by_uuid_endpoint(
    request: Request,  # Добавляем Request
    video_uuid: str,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """Получение видео по UUID"""
    check_admin_rate_limit(request)
    
    video = await get_video_by_uuid(db, video_uuid)
    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    return video

@router.get("/product/{product_id}", response_model=List[VideoResponse])
async def get_product_videos(
    request: Request,  # Добавляем Request
    product_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """Получение всех видео для продукта"""
    check_admin_rate_limit(request)
    
    videos = await get_videos_by_product_id(db, product_id)
    return videos

@router.get("/{video_id}/suggest-products")
async def suggest_products_for_video_endpoint(
    request: Request,  # Добавляем Request
    video_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """Предложение продуктов для привязки к видео"""
    check_admin_rate_limit(request)
    
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
        ],
        "requested_by": current_user.username
    }

# ========== ОБНОВЛЕНИЕ (для всех админов) ==========

@router.put("/{video_id}", response_model=VideoResponse)
async def update_video_endpoint(
    request: Request,  # Добавляем Request
    video_id: int,
    video_data: VideoUpdate,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """Обновление видео"""
    check_admin_rate_limit(request, max_requests=30, window_minutes=1)
    
    video = await get_video_by_id(db, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    
    # Логируем действие
    print(f"Admin {current_user.username} updating video {video_id} ('{video.title}')")
    
    updated_video = await update_video(db, video_id, video_data)
    
    print(f"SUCCESS: Video {video_id} updated by {current_user.username}")
    return updated_video

@router.post("/{video_id}/toggle-status", response_model=VideoResponse)
async def toggle_video_status_endpoint(
    request: Request,  # Добавляем Request
    video_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """Переключение статуса активности видео"""
    check_admin_rate_limit(request, max_requests=50, window_minutes=1)
    
    video = await get_video_by_id(db, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    
    # Логируем действие
    print(f"Admin {current_user.username} toggling video {video_id} status")
    
    updated_video = await toggle_video_status(db, video_id)
    return updated_video

@router.post("/{video_id}/toggle-featured", response_model=VideoResponse)
async def toggle_featured_status_endpoint(
    request: Request,  # Добавляем Request
    video_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """Переключение статуса избранного видео"""
    check_admin_rate_limit(request, max_requests=50, window_minutes=1)
    
    video = await get_video_by_id(db, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    
    # Логируем действие
    print(f"Admin {current_user.username} toggling video {video_id} featured status")
    
    updated_video = await toggle_featured_status(db, video_id)
    return updated_video

@router.post("/{video_id}/auto-link-product", response_model=VideoResponse)
async def auto_link_product_endpoint(
    request: Request,  # Добавляем Request
    video_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """Автоматическая привязка видео к продукту по названию"""
    check_admin_rate_limit(request, max_requests=30, window_minutes=1)
    
    video = await get_video_by_id(db, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    
    # Логируем действие
    print(f"Admin {current_user.username} auto-linking video {video_id} to product")
    
    updated_video = await auto_link_video_to_product(db, video_id)
    return updated_video

# ========== УДАЛЕНИЕ (только для суперадмина) ==========

@router.delete("/{video_id}")
async def delete_video_endpoint(
    request: Request,  # Добавляем Request
    video_id: int,
    current_user: AdminUser = Depends(get_current_superuser),  # ТОЛЬКО СУПЕРАДМИН!
    db: AsyncSession = Depends(get_db)
):
    """Удаление видео (только для суперадмина)"""
    check_admin_rate_limit(request, max_requests=10, window_minutes=1)
    
    video = await get_video_by_id(db, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    
    # КРИТИЧЕСКОЕ ДЕЙСТВИЕ - подробное логирование
    print(f"CRITICAL: Superuser {current_user.username} deleting video {video_id} ('{video.title}')")
    print(f"Video file: {video.url}")
    
    success = await delete_video(db, video_id)
    if success:
        print(f"SUCCESS: Video {video_id} ('{video.title}') deleted by superuser {current_user.username}")
        return {"message": f"Видео '{video.title}' успешно удалено"}
    else:
        print(f"ERROR: Failed to delete video {video_id}")
        raise HTTPException(status_code=500, detail="Ошибка удаления видео")

# ========== УПРАВЛЕНИЕ ЗАГРУЗКАМИ (только суперадмин) ==========

@router.get("/upload-stats/detailed")
async def get_detailed_upload_stats(
    request: Request,
    current_user: AdminUser = Depends(get_current_superuser)  # ТОЛЬКО СУПЕРАДМИН
):
    """Детальная статистика загрузок (только для суперадмина)"""
    check_admin_rate_limit(request, max_requests=10, window_minutes=1)
    
    return {
        "upload_stats_by_user": dict(video_upload_stats),
        "total_uploads_this_hour": sum(video_upload_stats.values()),
        "limits": {
            "per_user_per_hour": MAX_UPLOADS_PER_USER_PER_HOUR,
            "global_per_hour": MAX_UPLOADS_GLOBAL_PER_HOUR
        },
        "requested_by": current_user.username,
        "timestamp": datetime.utcnow()
    }

@router.post("/reset-upload-limits")
async def reset_upload_limits(
    request: Request,
    current_user: AdminUser = Depends(get_current_superuser)  # ТОЛЬКО СУПЕРАДМИН
):
    """Сброс лимитов загрузки (экстренная мера для суперадмина)"""
    check_admin_rate_limit(request, max_requests=3, window_minutes=5)
    
    # КРИТИЧЕСКОЕ ДЕЙСТВИЕ
    print(f"EMERGENCY: Superuser {current_user.username} resetting video upload limits")
    
    old_stats = dict(video_upload_stats)
    video_upload_stats.clear()
    
    print(f"SUCCESS: Upload limits reset by superuser {current_user.username}")
    
    return {
        "message": "Лимиты загрузки сброшены",
        "old_stats": old_stats,
        "reset_by": current_user.username,
        "timestamp": datetime.utcnow()
    }