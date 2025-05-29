import os
import subprocess
from pathlib import Path
from typing import Tuple, Optional
import uuid
from PIL import Image


class VideoProcessor:
    def __init__(self, media_root: str):
        self.media_root = Path(media_root)
        self.video_dir = self.media_root / "videos"
        self.thumbnail_dir = self.media_root / "thumbnails"
        
        # Создаем папки если не существуют
        self.video_dir.mkdir(exist_ok=True)
        self.thumbnail_dir.mkdir(exist_ok=True)

    def process_video(self, input_path: str, original_filename: str) -> dict:
        """
        Обрабатывает видео: сжимает, создает превью, возвращает информацию
        """
        file_uuid = str(uuid.uuid4())
        base_name = Path(original_filename).stem
        
        # Пути для выходных файлов
        output_filename = f"{file_uuid}_{base_name}.mp4"
        output_path = self.video_dir / output_filename
        thumbnail_filename = f"{file_uuid}_{base_name}_thumb.jpg"
        thumbnail_path = self.thumbnail_dir / thumbnail_filename
        
        try:
            # 1. Сжимаем и конвертируем видео
            duration = self._compress_video(input_path, str(output_path))
            
            # 2. Создаем превью
            self._create_thumbnail(str(output_path), str(thumbnail_path))
            
            # 3. Получаем размер файлов
            video_size = os.path.getsize(output_path)
            
            return {
                "video_path": f"/media/videos/{output_filename}",
                "thumbnail_path": f"/media/thumbnails/{thumbnail_filename}",
                "duration": duration,
                "file_size": video_size,
                "processed": True
            }
            
        except Exception as e:
            print(f"Ошибка обработки видео: {e}")
            # Если обработка не удалась, просто копируем оригинал
            return self._fallback_processing(input_path, original_filename)

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