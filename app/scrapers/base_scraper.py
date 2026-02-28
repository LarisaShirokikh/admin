"""
Базовый скрапер с полной синхронизацией продуктов:
  - Добавление новых
  - Обновление существующих
  - Деактивация отсутствующих на сайте-доноре
  - Скачивание и локальное хранение изображений
"""

import logging
import re
import time
from typing import Dict, List, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup
from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attributes import product_categories
from app.models.brand import Brand
from app.models.catalog import Catalog
from app.models.category import Category
from app.models.product import Product
from app.models.product_image import ProductImage
from app.schemas.product_image import ProductImageCreate
from app.services.image_service import ImageService
from app.scrapers.door_synonyms import DOOR_PATTERNS, DOOR_SYNONYMS, MORPHOLOGY_VARIANTS
from app.utils.text_utils import generate_slug


class BaseScraper:
    """Базовый класс для всех скраперов."""

    def __init__(
        self,
        brand_name: str,
        brand_slug: str,
        base_url: str,
        logger_name: str = "base_scraper",
    ):
        self.brand_name = brand_name
        self.brand_slug = brand_slug
        self.base_url = base_url
        self.logger = logging.getLogger(logger_name)
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            )
        }
        self._categories_cache: Optional[Dict] = None

    # ------------------------------------------------------------------ #
    #  HTTP
    # ------------------------------------------------------------------ #

    def get_html(self, url: str, retries: int = 3) -> Optional[str]:
        """Получает HTML страницы с повторными попытками."""
        url = self._abs_url(url)
        for attempt in range(retries):
            try:
                resp = requests.get(url, headers=self.headers, timeout=15)
                resp.raise_for_status()
                return resp.text
            except requests.RequestException as e:
                self.logger.warning("Попытка %d/%d — %s: %s", attempt + 1, retries, url, e)
                if attempt < retries - 1:
                    time.sleep(2 * (attempt + 1))
        self.logger.error("Не удалось загрузить: %s", url)
        return None

    def _abs_url(self, url: str) -> str:
        """Приводит URL к абсолютному."""
        if url.startswith("http"):
            return url
        return f"{self.base_url}/{url.lstrip('/')}"

    # ------------------------------------------------------------------ #
    #  Изображения
    # ------------------------------------------------------------------ #

    def collect_image_urls(self, urls_found: List[str]) -> List[str]:
        """Фильтрует и нормализует список URL изображений."""
        valid_ext = (".jpg", ".jpeg", ".png", ".webp", ".gif")
        seen: Set[str] = set()
        result: List[str] = []

        for raw in urls_found:
            if not raw or "data:image/svg" in raw:
                continue
            url = self._abs_url(raw)
            if not any(url.lower().endswith(ext) for ext in valid_ext):
                continue
            if url in seen:
                continue
            seen.add(url)
            result.append(url)

        return result

    def download_product_images(
        self,
        product_id: int,
        image_urls: List[str],
    ) -> List[dict]:
        """
        Скачивает все изображения продукта локально.

        Returns:
            Список dict: {url, original_url, is_local, is_main, file_size, download_error}
        """
        results = []
        for i, url in enumerate(image_urls):
            is_main = i == 0
            stored = ImageService.download_and_store(
                url=url,
                product_id=product_id,
                image_index=i,
                is_main=is_main,
            )

            if stored:
                results.append({
                    "url": stored["local_url"],
                    "original_url": url,
                    "is_local": True,
                    "is_main": is_main,
                    "file_size": stored["file_size"],
                    "download_error": None,
                })
            else:
                # Если не удалось скачать — сохраняем внешний URL как fallback
                results.append({
                    "url": url,
                    "original_url": url,
                    "is_local": False,
                    "is_main": is_main,
                    "file_size": None,
                    "download_error": "Download or conversion failed",
                })

        return results

    # ------------------------------------------------------------------ #
    #  Текст и цены
    # ------------------------------------------------------------------ #

    @staticmethod
    def extract_price(text: str) -> int:
        """Извлекает цену из текстовой строки."""
        if not text:
            return 0
        nums = re.findall(r"(\d[\s\d]*\d*)", text)
        prices = [int("".join(c for c in n if c.isdigit())) for n in nums if n]
        return max(prices) if prices else 0

    @staticmethod
    def make_meta_description(description: str, max_len: int = 500) -> str:
        """Формирует мета-описание из текста."""
        if not description:
            return ""
        # Берём часть до характеристик
        if "\n\nХарактеристики:" in description:
            description = description.split("\n\nХарактеристики:")[0]
        return description[:max_len]

    @staticmethod
    def calculate_prices(original_price: float) -> Tuple[float, float]:
        """Рассчитывает цену с наценкой 20% и цену со скидкой."""
        discount_price = float(original_price)
        price = round(discount_price * 1.2)
        return price, discount_price

    # ------------------------------------------------------------------ #
    #  БД: бренд, каталог
    # ------------------------------------------------------------------ #

    async def ensure_brand(self, db: AsyncSession) -> int:
        """Получает или создаёт бренд. Возвращает ID."""
        result = await db.execute(
            select(Brand).where(
                or_(
                    func.lower(Brand.name) == self.brand_name.lower(),
                    Brand.slug == self.brand_slug,
                )
            )
        )
        brand = result.scalar_one_or_none()
        if not brand:
            brand = Brand(name=self.brand_name, slug=self.brand_slug)
            db.add(brand)
            await db.flush()
            self.logger.info("Создан бренд: %s (ID: %d)", self.brand_name, brand.id)
        return brand.id

    async def ensure_catalog(
        self, db: AsyncSession, name: str, slug: str, brand_id: int
    ) -> Catalog:
        """Получает или создаёт каталог."""
        result = await db.execute(select(Catalog).where(Catalog.slug == slug))
        catalog = result.scalar_one_or_none()

        if catalog:
            changed = False
            if catalog.name != name:
                catalog.name = name
                changed = True
            if catalog.brand_id != brand_id:
                catalog.brand_id = brand_id
                changed = True
            if changed:
                await db.flush()
            return catalog

        # Создаём новый
        default_cat = await self._get_default_category(db)
        if not default_cat:
            raise ValueError("Нет активных категорий в БД")

        catalog = Catalog(
            name=name,
            slug=slug,
            category_id=default_cat.id,
            brand_id=brand_id,
            is_active=True,
        )
        db.add(catalog)
        await db.flush()
        self.logger.info("Создан каталог: %s (ID: %d)", name, catalog.id)
        return catalog

    # ------------------------------------------------------------------ #
    #  БД: создание / обновление / удаление продуктов
    # ------------------------------------------------------------------ #

    async def upsert_product(
        self,
        db: AsyncSession,
        *,
        name: str,
        slug: str,
        description: str,
        original_price: float,
        catalog_id: int,
        brand_id: int,
        image_urls: List[str],
        meta_title: str = "",
        meta_description: str = "",
        in_stock: bool = True,
    ) -> Optional[Product]:
        """
        Создаёт или обновляет продукт + скачивает картинки.
        Возвращает продукт.
        """
        price, discount_price = self.calculate_prices(original_price)

        # Ищем существующий
        result = await db.execute(
            select(Product).where(
                or_(
                    Product.slug == slug,
                    func.lower(Product.name) == name.lower(),
                )
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Обновляем поля
            existing.name = name
            existing.slug = slug
            existing.description = description
            existing.price = price
            existing.discount_price = discount_price
            existing.catalog_id = catalog_id
            existing.brand_id = brand_id
            existing.in_stock = in_stock
            existing.is_active = True
            if meta_title:
                existing.meta_title = meta_title
            if meta_description:
                existing.meta_description = meta_description

            await db.flush()

            # Обновляем картинки: скачиваем заново
            await self._sync_images(db, existing.id, image_urls)

            self.logger.info("Обновлён: %s (ID: %d)", name, existing.id)
            return existing

        # Создаём новый
        product = Product(
            name=name,
            slug=slug,
            description=description,
            price=price,
            discount_price=discount_price,
            catalog_id=catalog_id,
            brand_id=brand_id,
            in_stock=in_stock,
            is_active=True,
            meta_title=meta_title or name,
            meta_description=meta_description,
        )
        db.add(product)
        await db.flush()

        # Скачиваем картинки
        await self._sync_images(db, product.id, image_urls)

        self.logger.info("Создан: %s (ID: %d)", name, product.id)
        return product

    async def _sync_images(
        self, db: AsyncSession, product_id: int, image_urls: List[str]
    ) -> None:
        """Синхронизирует изображения: удаляет старые, скачивает новые."""
        # Удаляем старые записи в БД
        await db.execute(
            delete(ProductImage).where(ProductImage.product_id == product_id)
        )

        # Удаляем старые файлы с диска
        ImageService.delete_product_images(product_id)

        if not image_urls:
            return

        # Скачиваем и сохраняем
        downloaded = self.download_product_images(product_id, image_urls)

        for img_data in downloaded:
            db.add(ProductImage(
                product_id=product_id,
                url=img_data["url"],
                original_url=img_data["original_url"],
                is_local=img_data["is_local"],
                is_main=img_data["is_main"],
                file_size=img_data["file_size"],
                download_error=img_data["download_error"],
            ))

        await db.flush()

    async def deactivate_missing(
        self,
        db: AsyncSession,
        catalog_id: int,
        scraped_slugs: Set[str],
    ) -> int:
        """
        Деактивирует продукты, которые есть в БД но отсутствуют на сайте.
        Возвращает количество деактивированных.
        """
        result = await db.execute(
            select(Product.id, Product.slug).where(
                Product.catalog_id == catalog_id,
                Product.is_active == True,
                Product.slug.notin_(scraped_slugs) if scraped_slugs else True,
            )
        )
        to_deactivate = result.all()

        if not to_deactivate:
            return 0

        ids = [row.id for row in to_deactivate]
        await db.execute(
            update(Product)
            .where(Product.id.in_(ids))
            .values(is_active=False)
        )
        await db.flush()

        for row in to_deactivate:
            self.logger.info("Деактивирован (нет на сайте): %s", row.slug)

        return len(ids)

    # ------------------------------------------------------------------ #
    #  Категории
    # ------------------------------------------------------------------ #

    async def _get_default_category(self, db: AsyncSession) -> Optional[Category]:
        """Находит категорию по умолчанию."""
        for pattern in ["%все двери%", "%все товары%"]:
            result = await db.execute(
                select(Category).where(
                    func.lower(Category.name).like(pattern),
                    Category.is_active == True,
                )
            )
            cat = result.scalar_one_or_none()
            if cat:
                return cat

        # Fallback — первая активная
        result = await db.execute(
            select(Category).where(Category.is_active == True).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_categories(self, db: AsyncSession) -> Dict[str, Dict]:
        """Загружает все активные категории с ключевыми словами."""
        if self._categories_cache is not None:
            return self._categories_cache

        result = await db.execute(select(Category).where(Category.is_active == True))
        categories = result.scalars().all()

        cat_map = {}
        for cat in categories:
            keywords, patterns = self._build_category_keywords(cat)
            is_default = any(
                d in cat.name.lower()
                for d in ("все двери", "все товары", "default")
            )
            cat_map[cat.name.lower()] = {
                "id": cat.id,
                "name": cat.name,
                "slug": cat.slug,
                "keywords": keywords,
                "patterns": patterns,
                "is_default": is_default,
            }

        self._categories_cache = cat_map
        self.logger.info("Загружено %d категорий", len(cat_map))
        return cat_map

    def classify_product(
        self,
        text: str,
        categories: Dict[str, Dict],
        min_matches: int = 1,
    ) -> List[Dict]:
        """Классифицирует продукт по категориям на основе текста."""
        normalized = self._normalize_text(text)
        matched = []

        for _name, data in categories.items():
            if data.get("is_default"):
                continue

            weight = 0.0
            matches = 0

            for kw in data.get("keywords", []):
                if kw in normalized:
                    matches += 1
                    w = len(kw.split()) * 1.0
                    if len(kw.split()) > 1:
                        w *= 1.5
                    if kw == _name:
                        w *= 2.0
                    weight += w

            for pattern in data.get("patterns", []):
                try:
                    found = re.findall(pattern, normalized, re.IGNORECASE)
                    if found:
                        matches += len(found)
                        weight += len(found) * 1.5
                except re.error:
                    pass

            if matches >= min_matches:
                matched.append({
                    "id": data["id"],
                    "name": data["name"],
                    "weight": weight,
                    "matches": matches,
                })

        matched.sort(key=lambda x: x["weight"], reverse=True)
        return matched

    async def assign_categories(
        self,
        db: AsyncSession,
        product_id: int,
        default_category_id: int,
        additional: List[Dict],
        max_additional: int = 5,
    ) -> None:
        """Назначает продукт в категории."""
        # Очищаем старые связи
        await db.execute(
            delete(product_categories).where(
                product_categories.c.product_id == product_id
            )
        )

        assigned = set()

        # Обязательная категория
        await db.execute(
            insert(product_categories).values(
                product_id=product_id, category_id=default_category_id
            )
        )
        assigned.add(default_category_id)

        # Дополнительные
        for cat in additional[:max_additional]:
            if cat["id"] not in assigned:
                await db.execute(
                    insert(product_categories).values(
                        product_id=product_id, category_id=cat["id"]
                    )
                )
                assigned.add(cat["id"])

        await db.flush()

    async def update_category_counters(self, db: AsyncSession) -> None:
        """Обновляет счётчики товаров в категориях."""
        result = await db.execute(select(Category))
        for cat in result.scalars().all():
            count_result = await db.execute(
                select(func.count()).select_from(product_categories).where(
                    product_categories.c.category_id == cat.id
                )
            )
            if hasattr(Category, "product_count"):
                cat.product_count = count_result.scalar_one()
        await db.flush()

    # ------------------------------------------------------------------ #
    #  Главный метод синхронизации каталога
    # ------------------------------------------------------------------ #

    async def sync_catalog(
        self,
        catalog_url: str,
        db: AsyncSession,
    ) -> Dict:
        """
        Полная синхронизация одного каталога:
          1. Парсит все товары с сайта
          2. Добавляет новые / обновляет существующие (с картинками)
          3. Деактивирует отсутствующие
          4. Классифицирует по категориям

        Должен быть переопределён в дочерних классах через parse_catalog().
        """
        brand_id = await self.ensure_brand(db)
        all_categories = await self.get_categories(db)
        default_category = await self._get_default_category(db)

        if not default_category:
            self.logger.error("Нет категории по умолчанию!")
            return {"error": "No default category", "total": 0}

        # Парсим товары (реализация в дочернем классе)
        parsed_items = await self.parse_catalog(catalog_url, db, brand_id)
        if not parsed_items:
            self.logger.warning("Нет товаров в каталоге: %s", catalog_url)
            return {"new": 0, "updated": 0, "deactivated": 0, "total": 0}

        # Определяем catalog_id из первого товара
        catalog_id = parsed_items[0].get("catalog_id")
        scraped_slugs: Set[str] = set()

        new_count = 0
        updated_count = 0

        for item in parsed_items:
            try:
                slug = item["slug"]
                scraped_slugs.add(slug)

                # Проверяем существование
                result = await db.execute(
                    select(Product.id).where(Product.slug == slug)
                )
                is_new = result.scalar_one_or_none() is None

                # Создаём / обновляем
                product = await self.upsert_product(db, **item)
                if not product:
                    continue

                if is_new:
                    new_count += 1
                else:
                    updated_count += 1

                # Классификация
                analysis_text = f"{item['name']} {item.get('description', '')} {item.get('meta_title', '')}"
                additional_cats = self.classify_product(
                    analysis_text, all_categories
                )
                await self.assign_categories(
                    db, product.id, default_category.id, additional_cats
                )

            except Exception as e:
                self.logger.error("Ошибка товара %s: %s", item.get("name", "?"), e)
                continue

        # Деактивируем отсутствующие
        deactivated = 0
        if catalog_id and scraped_slugs:
            deactivated = await self.deactivate_missing(db, catalog_id, scraped_slugs)

        # Обновляем счётчики категорий
        await self.update_category_counters(db)

        await db.commit()

        stats = {
            "new": new_count,
            "updated": updated_count,
            "deactivated": deactivated,
            "total": new_count + updated_count,
        }
        self.logger.info(
            "Синхронизация %s: новых=%d, обновлено=%d, деактивировано=%d",
            catalog_url, new_count, updated_count, deactivated,
        )
        return stats

    async def sync_multiple_catalogs(
        self,
        catalog_urls: List[str],
        db: AsyncSession,
    ) -> int:
        total = 0
        for url in catalog_urls:
            try:
                stats = await self.sync_catalog(url, db)
                total += stats.get("total", 0)
            except Exception as e:
                self.logger.error("Ошибка каталога %s: %s", url, e, exc_info=True)
                await db.rollback()
        return total

    async def parse_multiple_catalogs(
        self, catalog_urls: List[str], db: AsyncSession
    ) -> int:
        return await self.sync_multiple_catalogs(catalog_urls, db)


    async def parse_catalog(
        self,
        catalog_url: str,
        db: AsyncSession,
        brand_id: int,
    ) -> List[Dict]:
        raise NotImplementedError


    def _build_category_keywords(self, cat: Category) -> Tuple[List[str], List[str]]:
        keywords: Set[str] = set()
        patterns: List[str] = []

        name_lower = cat.name.lower()
        keywords.add(name_lower)
        keywords.update(name_lower.split())

        if cat.slug:
            keywords.update(cat.slug.replace("-", " ").split())

        if hasattr(cat, "meta_keywords") and cat.meta_keywords:
            keywords.update(kw.strip().lower() for kw in cat.meta_keywords.split(","))

        # Синонимы
        for word in name_lower.split():
            if word in DOOR_SYNONYMS:
                keywords.update(DOOR_SYNONYMS[word])
            if word in MORPHOLOGY_VARIANTS:
                keywords.update(MORPHOLOGY_VARIANTS[word])

        # Паттерны
        for word in name_lower.split():
            if len(word) >= 4:
                root = word[: len(word) - 2]
                patterns.append(rf"\b{re.escape(root)}\w*\b")
            for key, plist in DOOR_PATTERNS.items():
                if key in word:
                    patterns.extend(plist)
                    break

        keywords = {k for k in keywords if k and len(k) > 1}
        return list(keywords), patterns

    @staticmethod
    def _normalize_text(text: str) -> str:
        if not text:
            return ""
        t = text.lower()
        t = re.sub(r"\s+", " ", t)
        for old, new in {"ё": "е", "—": "-", "–": "-"}.items():
            t = t.replace(old, new)
        return t.strip()

    def _build_product_text(self, item: Dict) -> str:
        parts = [
            item.get("name", ""),
            item.get("description", ""),
            item.get("meta_title", ""),
            item.get("meta_description", ""),
        ]
        return " ".join(p for p in parts if p)