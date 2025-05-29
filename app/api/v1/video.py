import tempfile
import os
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from app.deps import get_db
from app.crud.video import VideoProcessor, create_video
from app.schemas.video import VideoCreate

router = APIRouter()

# Инициализируем процессор видео
video_processor = VideoProcessor(media_root="/app/media")

@router.post("/upload/")
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = "",
    description: str = "",
    product_slug: str = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Загрузка и обработка видео
    """
    # Проверяем формат файла
    allowed_formats = ['.mp4', '.mov', '.avi', '.mkv', '.webm']
    file_extension = os.path.splitext(file.filename)[1].lower()
    
    if file_extension not in allowed_formats:
        raise HTTPException(400, f"Неподдерживаемый формат файла. Разрешены: {', '.join(allowed_formats)}")
    
    # Проверяем размер файла (например, макс 100MB)
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
        
        # Создаем запись в базе данных
        video_data = VideoCreate(
            title=title or f"Видео {file.filename}",
            description=description,
            url=processing_result["video_path"],
            thumbnail_url=processing_result["thumbnail_path"],
            duration=processing_result["duration"],
            product_slug=product_slug,
            is_active=True,
            is_featured=False
        )
        
        video = await create_video(db, video_data)
        
        return {
            "message": "Видео успешно загружено и обработано",
            "video_id": video.id,
            "video_url": processing_result["video_path"],
            "thumbnail_url": processing_result["thumbnail_path"],
            "duration": processing_result["duration"],
            "file_size_mb": round(processing_result["file_size"] / (1024 * 1024), 2),
            "processed": processing_result["processed"]
        }
        
    except Exception as e:
        raise HTTPException(500, f"Ошибка обработки видео: {str(e)}")
    
    finally:
        # Удаляем временный файл
        if os.path.exists(temp_path):
            os.unlink(temp_path)