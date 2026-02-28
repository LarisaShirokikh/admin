"""
ImageService — скачивание, конвертация в WebP и локальное хранение изображений.

Используется:
  - скраперами при парсинге (скачивание сразу при импорте)
  - Celery задачей для миграции старых внешних картинок
  - API для ручного управления
"""

import hashlib
import logging
import os
import shutil
from io import BytesIO
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from PIL import Image

logger = logging.getLogger("image_service")

MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", "/app/media"))
PRODUCTS_DIR = MEDIA_ROOT / "products"

# Настройки
WEBP_QUALITY = 85
MAX_IMAGE_SIZE = (1920, 1920)
DOWNLOAD_TIMEOUT = 15
MAX_FILE_SIZE = 10 * 1024 * 1024

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


class ImageService:

    @staticmethod
    def get_product_dir(product_id: int) -> Path:
        path = PRODUCTS_DIR / str(product_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def get_local_url(product_id: int, filename: str) -> str:
        """Формирует локальный URL для отдачи через nginx."""
        return f"/media/products/{product_id}/{filename}"

    @staticmethod
    def download_image(url: str) -> Optional[bytes]:
        """
        Скачивает изображение по URL.
        Возвращает bytes или None при ошибке.
        """
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=DOWNLOAD_TIMEOUT,
                stream=True,
            )
            response.raise_for_status()

            # Проверяем Content-Type
            content_type = response.headers.get("Content-Type", "")
            if not content_type.startswith("image/"):
                logger.warning("Не изображение: %s (Content-Type: %s)", url, content_type)
                return None

            # Проверяем размер
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_FILE_SIZE:
                logger.warning("Файл слишком большой: %s (%s bytes)", url, content_length)
                return None

            data = response.content
            if len(data) < 100:
                logger.warning("Файл слишком маленький: %s (%d bytes)", url, len(data))
                return None

            return data

        except requests.exceptions.RequestException as e:
            logger.warning("Ошибка скачивания %s: %s", url, e)
            return None

    @staticmethod
    def convert_to_webp(image_data: bytes) -> Optional[bytes]:
        try:
            img = Image.open(BytesIO(image_data))

            if img.mode in ("RGBA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            img.thumbnail(MAX_IMAGE_SIZE, Image.LANCZOS)

            output = BytesIO()
            img.save(output, format="WEBP", quality=WEBP_QUALITY, method=4)
            return output.getvalue()

        except Exception as e:
            logger.warning("Ошибка конвертации в WebP: %s", e)
            return None

    @classmethod
    def download_and_store(
        cls,
        url: str,
        product_id: int,
        image_index: int,
        is_main: bool = False,
    ) -> Optional[dict]:
        image_data = cls.download_image(url)
        if not image_data:
            return None

        webp_data = cls.convert_to_webp(image_data)
        if not webp_data:
            return None

        filename = f"{'main' if is_main else str(image_index)}.webp"
        product_dir = cls.get_product_dir(product_id)
        file_path = product_dir / filename

        try:
            file_path.write_bytes(webp_data)
        except OSError as e:
            logger.error("Ошибка записи файла %s: %s", file_path, e)
            return None

        local_url = cls.get_local_url(product_id, filename)
        file_size = len(webp_data)

        logger.info(
            "Сохранено: %s → %s (%d KB)",
            url[:80],
            local_url,
            file_size // 1024,
        )

        return {
            "local_url": local_url,
            "original_url": url,
            "file_size": file_size,
            "filename": filename,
        }

    @classmethod
    def delete_product_images(cls, product_id: int) -> bool:
        product_dir = PRODUCTS_DIR / str(product_id)
        if product_dir.exists():
            try:
                shutil.rmtree(product_dir)
                logger.info("Удалены изображения продукта %d", product_id)
                return True
            except OSError as e:
                logger.error("Ошибка удаления %s: %s", product_dir, e)
                return False
        return True

    @classmethod
    def get_disk_usage(cls) -> dict:
        total_size = 0
        total_files = 0
        total_products = 0

        if PRODUCTS_DIR.exists():
            for product_dir in PRODUCTS_DIR.iterdir():
                if product_dir.is_dir():
                    total_products += 1
                    for f in product_dir.iterdir():
                        if f.is_file():
                            total_files += 1
                            total_size += f.stat().st_size

        return {
            "total_size_mb": round(total_size / (1024 * 1024), 1),
            "total_files": total_files,
            "total_products": total_products,
        }