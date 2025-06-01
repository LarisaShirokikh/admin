# app/crud/video.py
import os
import subprocess
import uuid
import re
from pathlib import Path
from typing import Optional, List
from difflib import SequenceMatcher
from sqlalchemy import and_, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.video import Video
from app.models.product import Product
from app.schemas.video import VideoCreate, VideoUpdate


class VideoProcessor:
    def __init__(self, media_root: str):
        self.media_root = Path(media_root)
        self.video_dir = self.media_root / "videos"
        self.thumbnail_dir = self.media_root / "thumbnails"
        
        # Создаем папки если не существуют
        self.video_dir.mkdir(exist_ok=True)
        self.thumbnail_dir.mkdir(exist_ok=True)

    def process_video(self, input_path: str, original_filename: str) -> dict:
        """ПРОСТОЕ копирование файла без FFmpeg"""
        import shutil
        
        file_uuid = str(uuid.uuid4())
        base_name = Path(original_filename).stem
        
        # Всегда сохраняем как .mp4 для веба
        output_filename = f"{file_uuid}_{base_name}.mp4"
        output_path = self.video_dir / output_filename
        
        try:
            # Просто копируем файл
            shutil.copy2(input_path, output_path)
            
            # Пытаемся установить права (может не сработать из-за Docker)
            try:
                os.chmod(output_path, 0o644)
            except:
                pass  # Игнорируем ошибку, исправим в роутере
            
            file_size = os.path.getsize(output_path)
            
            return {
                "video_path": f"/media/videos/{output_filename}",
                "thumbnail_path": None,
                "duration": None,
                "file_size": file_size,
                "processed": False
            }
            
        except Exception as e:
            print(f"Ошибка копирования файла: {e}")
            raise


    def _quick_convert_mov_to_mp4(self, input_path: str, output_path: str):
        """Быстрая конвертация MOV → MP4 без сжатия"""
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-c', 'copy',  # Копируем потоки без перекодирования!
            '-movflags', '+faststart',  # Для веб-стриминга
            output_path
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, timeout=60)  # 1 минута макс
        except:
            # Если не получилось, просто копируем
            import shutil
            shutil.copy2(input_path, output_path)

    def _compress_video(self, input_path: str, output_path: str) -> Optional[float]:
        """
        Сжимает видео с оптимальными настройками для веба
        """
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            # Видео кодек H.264 для лучшей совместимости
            '-c:v', 'libx264',
            # Аудио кодек AAC
            '-c:a', 'aac',
            # Битрейт видео (чем меньше, тем меньше размер)
            '-b:v', '1000k',
            # Битрейт аудио
            '-b:a', '128k',
            # Ограничиваем разрешение (макс 1080p)
            '-vf', 'scale=min(1920\\,iw):min(1080\\,ih):force_original_aspect_ratio=decrease',
            # Оптимизация для веб-стриминга
            '-movflags', '+faststart',
            # Профиль для лучшей совместимости
            '-profile:v', 'main',
            '-preset', 'medium',
            output_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)  # 5 минут таймаут
            if result.returncode != 0:
                print(f"FFmpeg error: {result.stderr}")
                return None
                
            # Получаем длительность видео
            return self._get_video_duration(output_path)
            
        except subprocess.TimeoutExpired:
            print("Таймаут обработки видео")
            return None
        except Exception as e:
            print(f"Ошибка FFmpeg: {e}")
            return None

    def _create_thumbnail(self, video_path: str, thumbnail_path: str):
        """
        Создает превью из первой секунды видео
        """
        cmd = [
            'ffmpeg', '-y', '-i', video_path,
            '-ss', '00:00:01.000',  # Берем кадр с 1 секунды
            '-vframes', '1',
            '-vf', 'scale=320:240:force_original_aspect_ratio=decrease',
            thumbnail_path
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, timeout=30)
        except Exception as e:
            print(f"Ошибка создания превью: {e}")

    def _get_video_duration(self, video_path: str) -> Optional[float]:
        """
        Получает длительность видео в секундах
        """
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'compact=print_section=0:nokey=1:escape=csv',
            '-show_entries', 'format=duration', video_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception as e:
            print(f"Ошибка получения длительности: {e}")
        
        return None

    def _fallback_processing(self, input_path: str, original_filename: str) -> dict:
        """
        Запасной вариант если FFmpeg не работает
        """
        import shutil
        
        file_uuid = str(uuid.uuid4())
        output_filename = f"{file_uuid}_{original_filename}"
        output_path = self.video_dir / output_filename
        
        # Просто копируем файл
        shutil.copy2(input_path, output_path)
        
        return {
            "video_path": f"/media/videos/{output_filename}",
            "thumbnail_path": None,
            "duration": None,
            "file_size": os.path.getsize(output_path),
            "processed": False
        }


# CRUD функции для работы с видео

async def create_video(db: AsyncSession, video_data: VideoCreate) -> Video:
    """Создание нового видео"""
    video = Video(**video_data.dict())
    db.add(video)
    await db.commit()
    await db.refresh(video)
    return video

async def get_video_by_id(db: AsyncSession, video_id: int) -> Optional[Video]:
    """Получение видео по ID"""
    result = await db.execute(
        select(Video).where(Video.id == video_id)
    )
    return result.scalar_one_or_none()

async def get_video_by_uuid(db: AsyncSession, video_uuid: str) -> Optional[Video]:
    """Получение видео по UUID"""
    result = await db.execute(
        select(Video).where(Video.uuid == video_uuid)
    )
    return result.scalar_one_or_none()

async def get_videos(
    db: AsyncSession, 
    skip: int = 0, 
    limit: int = 100,
    is_active: Optional[bool] = None,
    is_featured: Optional[bool] = None,
    product_id: Optional[int] = None
) -> List[Video]:
    """Получение списка видео с фильтрами"""
    query = select(Video)
    
    filters = []
    if is_active is not None:
        filters.append(Video.is_active == is_active)
    if is_featured is not None:
        filters.append(Video.is_featured == is_featured)
    if product_id is not None:
        filters.append(Video.product_id == product_id)
    
    if filters:
        query = query.where(and_(*filters))
    
    query = query.offset(skip).limit(limit).order_by(Video.created_at.desc())
    
    result = await db.execute(query)
    return result.scalars().all()

async def get_videos_by_product_id(db: AsyncSession, product_id: int) -> List[Video]:
    """Получение всех видео для продукта"""
    result = await db.execute(
        select(Video)
        .where(Video.product_id == product_id)
        .order_by(Video.created_at.desc())
    )
    return result.scalars().all()

async def search_videos(db: AsyncSession, query_text: str) -> List[Video]:
    """Поиск видео по названию и описанию"""
    result = await db.execute(
        select(Video)
        .where(
            and_(
                Video.is_active == True,
                Video.title.ilike(f'%{query_text}%')
            )
        )
        .order_by(Video.created_at.desc())
    )
    return result.scalars().all()

async def update_video(db: AsyncSession, video_id: int, video_data: VideoUpdate) -> Optional[Video]:
    """Обновление видео"""
    # Получаем только заполненные поля
    update_data = {k: v for k, v in video_data.dict().items() if v is not None}
    
    if not update_data:
        return await get_video_by_id(db, video_id)
    
    await db.execute(
        update(Video)
        .where(Video.id == video_id)
        .values(**update_data)
    )
    await db.commit()
    
    return await get_video_by_id(db, video_id)

async def delete_video(db: AsyncSession, video_id: int) -> bool:
    """Удаление видео"""
    # Получаем видео для удаления файлов
    video = await get_video_by_id(db, video_id)
    if not video:
        return False
    
    # Удаляем файлы
    delete_video_files(video.url, video.thumbnail_url)
    
    # Удаляем запись из БД
    result = await db.execute(
        delete(Video).where(Video.id == video_id)
    )
    await db.commit()
    
    return result.rowcount > 0

async def toggle_video_status(db: AsyncSession, video_id: int) -> Optional[Video]:
    """Переключение статуса активности видео"""
    video = await get_video_by_id(db, video_id)
    if not video:
        return None
    
    new_status = not video.is_active
    return await update_video(db, video_id, VideoUpdate(is_active=new_status))

async def toggle_featured_status(db: AsyncSession, video_id: int) -> Optional[Video]:
    """Переключение статуса избранного видео"""
    video = await get_video_by_id(db, video_id)
    if not video:
        return None
    
    new_status = not video.is_featured
    return await update_video(db, video_id, VideoUpdate(is_featured=new_status))

async def find_product_by_title(db: AsyncSession, video_title: str) -> Optional[Product]:
    """
    Улучшенный поиск продукта по названию видео
    """
    # Очищаем название от лишних символов
    cleaned_title = re.sub(r'[^\w\s]', '', video_title.lower()).strip()
    
    # Получаем все активные продукты
    result = await db.execute(
        select(Product).where(Product.is_active == True)
    )
    products = result.scalars().all()
    
    best_match = None
    best_score = 0
    
    for product in products:
        product_name = re.sub(r'[^\w\s]', '', product.name.lower()).strip()
        
        # Проверяем точное вхождение
        if product_name in cleaned_title or cleaned_title in product_name:
            return product
        
        # Вычисляем схожесть строк
        similarity = SequenceMatcher(None, cleaned_title, product_name).ratio()
        
        if similarity > best_score and similarity > 0.6:  # порог схожести 60%
            best_score = similarity
            best_match = product
    
    return best_match

async def auto_link_video_to_product(db: AsyncSession, video_id: int) -> Optional[Video]:
    """Автоматическая привязка видео к продукту по названию"""
    video = await get_video_by_id(db, video_id)
    if not video or video.product_id:
        return video  # Уже привязано к продукту
    
    # Ищем подходящий продукт
    product = await find_product_by_title(db, video.title)
    if product:
        return await update_video(db, video_id, VideoUpdate(product_id=product.id))
    
    return video

async def suggest_products_for_video(db: AsyncSession, video_title: str, limit: int = 5) -> List[tuple]:
    """
    Предложение продуктов для привязки к видео
    Возвращает список кортежей (product, score)
    """
    cleaned_title = re.sub(r'[^\w\s]', '', video_title.lower()).strip()
    
    result = await db.execute(
        select(Product).where(Product.is_active == True)
    )
    products = result.scalars().all()
    
    suggestions = []
    
    for product in products:
        product_name = re.sub(r'[^\w\s]', '', product.name.lower()).strip()
        similarity = SequenceMatcher(None, cleaned_title, product_name).ratio()
        
        if similarity > 0.3:  # минимальная схожесть 30%
            suggestions.append((product, similarity))
    
    # Сортируем по убыванию схожести
    suggestions.sort(key=lambda x: x[1], reverse=True)
    
    return suggestions[:limit]

def delete_video_files(video_url: str, thumbnail_url: Optional[str] = None):
    """Удаление файлов видео и превью"""
    media_root = Path("/app/media")
    
    # Удаляем видео файл
    if video_url and video_url.startswith("/media/"):
        video_path = media_root / video_url[7:]  # убираем /media/
        if video_path.exists():
            try:
                video_path.unlink()
            except Exception as e:
                print(f"Ошибка удаления видео файла {video_path}: {e}")
    
    # Удаляем превью
    if thumbnail_url and thumbnail_url.startswith("/media/"):
        thumbnail_path = media_root / thumbnail_url[7:]  # убираем /media/
        if thumbnail_path.exists():
            try:
                thumbnail_path.unlink()
            except Exception as e:
                print(f"Ошибка удаления превью {thumbnail_path}: {e}")

async def get_featured_videos(db: AsyncSession, limit: int = 10) -> List[Video]:
    """Получение избранных видео"""
    result = await db.execute(
        select(Video)
        .where(and_(Video.is_active == True, Video.is_featured == True))
        .order_by(Video.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()