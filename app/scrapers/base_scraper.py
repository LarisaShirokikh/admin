"""
Базовый модуль с общими компонентами для всех скраперов
"""
import logging
import re
import json
from typing import List, Dict, Any, Optional, Set, Tuple
from bs4 import BeautifulSoup
import requests
from sqlalchemy import func, insert, or_, select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.text_utils import clean_text, generate_slug
from app.crud.product import create_or_update_product
from app.data.categories_data import CATEGORY_KEYWORDS
from app.models.catalog import Catalog
from app.models.category import Category
from app.models.brand import Brand
from app.models.product import Product
from app.schemas.product import ProductCreate
from app.schemas.product_image import ProductImageCreate
from app.models.attributes import product_categories

# Базовый класс для скраперов
class BaseScraper:
    def __init__(self, 
                 brand_name: str, 
                 brand_slug: str, 
                 base_url: str,
                 logger_name: str = "base_scraper"):
        """
        Инициализирует базовый скрапер
        
        Args:
            brand_name: Название бренда
            brand_slug: Slug бренда
            base_url: Базовый URL сайта
            logger_name: Имя логгера
        """
        self.brand_name = brand_name
        self.brand_slug = brand_slug
        self.base_url = base_url
        self.logger = logging.getLogger(logger_name)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
    # ---------- Методы работы с HTTP и HTML ----------
    
    def get_html_content(self, url: str, retry_count: int = 3) -> Optional[str]:
        """
        Получает HTML-контент страницы по URL с повторными попытками при ошибках
        """
        if not url.startswith('http'):
            url = f"{self.base_url}{url}" if url.startswith('/') else f"{self.base_url}/{url}"
            
        for attempt in range(retry_count):
            try:
                self.logger.info(f"Запрос к URL (попытка {attempt+1}): {url}")
                response = requests.get(url, headers=self.headers, timeout=15)
                response.raise_for_status()
                return response.text
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Ошибка при запросе к {url}: {e}")
                if attempt < retry_count - 1:
                    self.logger.info(f"Повторная попытка через {2 * (attempt + 1)} секунд...")
                    import time
                    time.sleep(2 * (attempt + 1))
                else:
                    self.logger.error(f"Не удалось получить контент после {retry_count} попыток")
        
        return None
    
    def normalize_url(self, url: str) -> str:
        """Нормализует URL, добавляя базовый URL при необходимости"""
        if not url.startswith('http'):
            return f"{self.base_url}{url}" if url.startswith('/') else f"{self.base_url}/{url}"
        return url
    
    # ---------- Методы работы с изображениями ----------
    
    def add_image_url_if_valid(self, image_urls: List[str], raw_url: str) -> None:
        """
        Проверяет и добавляет URL изображения в список, если он валидный
        """
        valid_extensions = (".jpg", ".jpeg", ".png", ".webp", ".gif")

        if not raw_url or "data:image/svg+xml" in raw_url:
            return

        # Проверяем, является ли URL абсолютным
        full_url = raw_url
        if not raw_url.startswith('http'):
            clean_url = raw_url.lstrip('/')
            full_url = f"{self.base_url}/{clean_url}"

        # Проверяем расширение файла
        if not any(full_url.lower().endswith(ext) for ext in valid_extensions):
            return

        if full_url in image_urls:
            return

        image_urls.append(full_url)
        self.logger.info(f"Добавлено изображение: {full_url}")
    
    def create_image_objects(self, image_urls: List[str], main_image_url: Optional[str] = None) -> List[ProductImageCreate]:
        """Создает объекты изображений, ставя основное изображение первым"""
        if main_image_url and main_image_url in image_urls:
            # Удаляем main_image_url из списка
            image_urls.remove(main_image_url)
            # Добавляем его в начало
            image_urls.insert(0, main_image_url)
        
        return [ProductImageCreate(url=img, is_main=(i == 0)) for i, img in enumerate(image_urls)]
    
    # ---------- Методы работы с текстом ----------
    
    def extract_price_from_text(self, text: str) -> int:
        """Извлекает цену из текста"""
        if not text:
            return 0
        
        matches = re.findall(r'(\d+[\s\d]*\d*)', text)
        prices = [int(''.join(c for c in match if c.isdigit())) for match in matches if match]
        return max(prices) if prices else 0
    
    def create_meta_description(self, description: str, characteristics: Dict[str, str]) -> str:
        """Создает мета-описание на основе описания и характеристик"""
        meta_description = description
        if characteristics:
            chars_text = ". ".join([f"{key}: {value}" for key, value in characteristics.items()])
            if len(meta_description) + len(chars_text) <= 490:
                meta_description = f"{meta_description}. {chars_text}"
        
        return meta_description[:500]
    
    # ---------- Методы работы с базой данных ----------
    
    async def ensure_brand_exists(self, db: AsyncSession) -> int:
        """
        Проверяет существование бренда и создает его, если нет
        Возвращает ID бренда
        """
        # Ищем бренд по имени или slug
        result = await db.execute(
            select(Brand).where(
                or_(
                    func.lower(Brand.name) == self.brand_name.lower(),
                    Brand.slug == self.brand_slug
                )
            )
        )
        brand = result.scalar_one_or_none()
        
        if not brand:
            # Создаем новый бренд
            brand = Brand(
                name=self.brand_name,
                slug=self.brand_slug
            )
            db.add(brand)
            await db.flush()
            self.logger.info(f"Создан новый бренд: {self.brand_name}")
        
        return brand.id
    
    async def get_or_create_catalog(self, db: AsyncSession, catalog_name: str, catalog_slug: str, brand_id: int) -> Catalog:
        """
        Получает или создает каталог с привязкой к бренду
        
        Args:
            db: Сессия базы данных
            catalog_name: Название каталога
            catalog_slug: Slug каталога
            brand_id: ID бренда
            
        Returns:
            Объект каталога
        """
        result = await db.execute(select(Catalog).where(Catalog.slug == catalog_slug))
        catalog = result.scalar_one_or_none()
        
        if not catalog:
            # Получаем категорию по умолчанию
            default_category = await self.get_default_category(db, brand_id)
            
            # Создаем новый каталог с привязкой к бренду
            catalog = Catalog(
                name=catalog_name,
                slug=catalog_slug,
                category_id=default_category.id,
                brand_id=brand_id,  # Добавляем привязку к бренду
                is_active=True
            )
            db.add(catalog)
            await db.flush()
            self.logger.info(f"Создан новый каталог: {catalog_name} (бренд ID: {brand_id})")
        else:
            # Проверяем необходимость обновления
            update_needed = False
            
            if catalog.name != catalog_name:
                catalog.name = catalog_name
                update_needed = True
                
            # Обновляем brand_id, если он отличается или не установлен
            if catalog.brand_id != brand_id:
                catalog.brand_id = brand_id
                update_needed = True
                
            if update_needed:
                db.add(catalog)
                await db.flush()
                self.logger.info(f"Обновлен существующий каталог: {catalog_name} (бренд ID: {brand_id})")
        
        return catalog
    
    async def get_default_category(self, db: AsyncSession, brand_id: int) -> Category:
        """Получает или создает категорию по умолчанию 'Все двери'"""
        # Сначала пробуем найти по slug
        result = await db.execute(select(Category).where(Category.slug == "vse-dveri"))
        default_category = result.scalar_one_or_none()
        
        # Если не нашли по slug, ищем по названию (для обратной совместимости)
        if not default_category:
            result = await db.execute(select(Category).where(
                func.lower(Category.name) == "все двери"
            ))
            default_category = result.scalar_one_or_none()
        
        # Если все еще не нашли, создаем новую категорию
        if not default_category:
            default_category = Category(
                name="Все двери",
                slug="vse-dveri",
                brand_id=brand_id,
                meta_title="Все двери - Купить двери в магазине",
                meta_description="Широкий выбор дверей всех типов. Высокое качество, доступные цены, гарантия от производителя.",
                meta_keywords="двери, купить двери, входные двери, межкомнатные двери",
                is_active=True
            )
            db.add(default_category)
            await db.flush()
            self.logger.info("Создана категория по умолчанию 'Все двери'")
        
        return default_category
    
    async def update_catalog_image(self, db: AsyncSession, catalog: Catalog, image_url: str) -> None:
        """Обновляет изображение каталога"""
        catalog.image = image_url
        db.add(catalog)
        await db.flush()
        self.logger.info(f"Обновлено изображение для каталога {catalog.name}: {image_url}")

    async def update_catalogs_brand_id(self, db: AsyncSession, brand_id: int) -> None:
        """
        Обновляет brand_id для всех каталогов бренда, у которых он не установлен
        
        Args:
            db: Сессия базы данных
            brand_id: ID бренда
        """
        # Получаем все каталоги без привязки к бренду
        result = await db.execute(
            select(Catalog).where(Catalog.brand_id.is_(None))
        )
        catalogs = result.scalars().all()
        
        updated_count = 0
        for catalog in catalogs:
            # Находим продукты каталога
            products_result = await db.execute(
                select(Product).where(Product.catalog_id == catalog.id)
            )
            products = products_result.scalars().all()
            
            # Анализируем бренд продуктов
            brand_ids = set(product.brand_id for product in products if product.brand_id)
            
            # Если все продукты имеют одинаковый бренд и он совпадает с текущим
            if len(brand_ids) == 1 and brand_id in brand_ids:
                catalog.brand_id = brand_id
                updated_count += 1
            # Если продуктов нет или у них разные бренды, устанавливаем текущий бренд
            elif not brand_ids:
                catalog.brand_id = brand_id
                updated_count += 1
        
        if updated_count > 0:
            await db.flush()
            self.logger.info(f"Обновлено {updated_count} каталогов с привязкой к бренду ID: {brand_id}")
        
        # Дополнительно проверяем, чтобы все товары этого бренда были в категории "все двери"
        await self.ensure_products_in_default_category(db, brand_id)

    async def get_or_create_default_category(self, db: AsyncSession, brand_id: Optional[int] = None) -> Category:
        """Получает или создает категорию 'все двери'"""
        # Ищем категорию по имени
        result = await db.execute(
            select(Category).where(
                func.lower(Category.name) == "все двери"
            )
        )
        default_category = result.scalar_one_or_none()
        
        # Если не нашли, создаем новую
        if not default_category:
            # Получаем метаданные из CATEGORY_KEYWORDS
            meta_data = {}
            for cat_name, cat_data in CATEGORY_KEYWORDS.items():
                if cat_name.lower() == "все двери":
                    meta_data = cat_data
                    break
                    
            # Создаем категорию
            default_category = Category(
                name="Все двери",
                slug="vse-dveri",
                brand_id=brand_id,
                meta_title=meta_data.get("meta_title", "Все двери - Полный каталог"),
                meta_description=meta_data.get("meta_description", "Полный каталог дверей всех типов и стилей."),
                meta_keywords=meta_data.get("meta_keywords", "двери, входные двери, межкомнатные двери"),
                image_url=meta_data.get("image_url", ""),
                is_active=True
            )
            db.add(default_category)
            await db.flush()
            self.logger.info(f"Создана категория 'Все двери' (ID: {default_category.id})")
        
        return default_category

    async def add_product_to_category(self, db: AsyncSession, product_id: int, category_id: int, is_primary: bool = True) -> None:
        """
        Добавляет продукт в указанную категорию
        
        Args:
            db: Сессия базы данных
            product_id: ID продукта
            category_id: ID категории
            is_primary: Является ли категория основной для продукта
        """
        # Проверяем, есть ли товар в категории
        result = await db.execute(
            select(func.count()).select_from(product_categories).where(
                product_categories.c.product_id == product_id,
                product_categories.c.category_id == category_id
            )
        )
        count = result.scalar_one()
        
        # Если товара нет в категории, добавляем
        if count == 0:
            values = {
                'product_id': product_id,
                'category_id': category_id
            }
            
            # Если таблица поддерживает флаг is_primary
            if hasattr(product_categories.c, 'is_primary'):
                values['is_primary'] = is_primary
                
            stmt = insert(product_categories).values(**values)
            await db.execute(stmt)
            self.logger.debug(f"Продукт ID:{product_id} добавлен в категорию ID:{category_id}")

    async def classify_product_additional_categories(self, db: AsyncSession, product_id: int, text_to_analyze: str, category_map: Dict[str, Dict]) -> None:
        """
        Классифицирует продукт по дополнительным категориям, кроме 'все двери'
        
        Args:
            db: Сессия базы данных
            product_id: ID продукта
            text_to_analyze: Текст для анализа
            category_map: Словарь с данными категорий
        """
        # Приводим текст к нижнему регистру для анализа
        text_to_analyze = text_to_analyze.lower()
        
        # Для каждой категории проверяем наличие ключевых слов
        for category_name, category_data in category_map.items():
            # Пропускаем категорию "все двери" - продукт уже добавлен в неё
            if category_name.lower() == "все двери":
                continue
                
            category_id = category_data.get('id')
            if not category_id:
                continue
            
            # Получаем ключевые слова
            keywords = category_data.get('keywords', [])
            
            # Проверяем вхождение ключевых слов
            matches = 0
            for keyword in keywords:
                if keyword.lower() in text_to_analyze:
                    matches += 1
            
            # Если есть хотя бы одно совпадение, добавляем в категорию
            if matches > 0:
                await self.add_product_to_category(db, product_id, category_id, is_primary=False)
                self.logger.info(f"Продукт ID:{product_id} добавлен в дополнительную категорию '{category_name}' (найдено {matches} совпадений)")
    
    # ---------- Методы работы с категориями ----------
    
    async def ensure_categories_exist(self, db: AsyncSession, brand_id: int) -> None:
        """Создаёт необходимые категории в базе данных"""
        # Загружаем существующие категории
        result = await db.execute(select(Category))
        categories = result.scalars().all()
        categories_dict = {category.name.lower(): category for category in categories}
        
        # Создаём недостающие категории
        for category_name, category_data in CATEGORY_KEYWORDS.items():
            if category_name.lower() not in categories_dict:
                # Транслитерация для slug
                slug = generate_slug(category_name)
                
                new_category = Category(
                    name=category_name.title(),  # Преобразуем первые буквы слов в заглавные
                    brand_id=brand_id, 
                    slug=slug,  # Генерируем slug
                    meta_title=category_data.get("meta_title", f"{category_name.title()} - Купить в магазине {self.brand_name}"),
                    meta_description=category_data.get("meta_description", f"Широкий выбор товаров из категории {category_name}. Высокое качество, доступные цены, гарантия от производителя."),
                    meta_keywords=category_data.get("meta_keywords", f"{category_name}, купить {category_name}, {category_name} от производителя"),
                    image_url=category_data.get("image_url", "")
                )
                
                # Если нужны дополнительные поля
                if hasattr(Category, 'is_active'):
                    new_category.is_active = True
                
                db.add(new_category)
                await db.flush()
                self.logger.info(f"Создана новая категория: {category_name.title()}")
    
    async def get_category_map(self, db: AsyncSession) -> Dict[str, Dict]:
        """Получает маппинг категорий и их ключевых слов"""
        result = await db.execute(select(Category))
        categories = result.scalars().all()
        
        # Создаем маппинг имен категорий к их ID и ключевым словам
        category_map = {}
        for category in categories:
            category_name = category.name.lower()
            # Ищем ключевые слова для этой категории
            keywords = []
            for name, kws in CATEGORY_KEYWORDS.items():
                if name.lower() == category_name:
                    keywords = kws.get('keywords', [])
                    break
            
            category_map[category_name] = {
                'id': category.id,
                'keywords': keywords
            }
        
        return category_map
    
    async def classify_product(self, db: AsyncSession, product_id: int, text_to_analyze: str, category_map: Dict[str, Dict]) -> Set[int]:
        """
        Классифицирует продукт по категориям на основе текста.
        Возвращает набор ID категорий, в которые следует добавить продукт
        (кроме категории 'все двери', которая добавляется отдельно)
        """
        category_ids = set()
        text_to_analyze = text_to_analyze.lower()
        
        # Получаем данные о продукте
        product_result = await db.execute(select(Product).where(Product.id == product_id))
        product = product_result.scalar_one_or_none()
        
        # Дополнительный буст для брендов (можно настроить для каждого бренда)
        brand_boosts = {}
        if product and product.brand_id:
            brand_result = await db.execute(select(Brand).where(Brand.id == product.brand_id))
            brand = brand_result.scalar_one_or_none()
            if brand:
                brand_name = brand.name.lower()
                # Задаем бонусы для определенных брендов в определенных категориях
                if brand_name == "лабиринт":
                    brand_boosts = {
                        "двери для квартиры": 1.5,
                        "металлические двери": 1.5
                    }
                elif brand_name == "интекрон":
                    brand_boosts = {
                        "двери с электро замком": 1.5,
                        "двери с терморазрывом": 1.3
                    }
        
        # Анализируем каждую категорию
        for category_name, category_data in category_map.items():
            # Пропускаем категорию "все двери" - она добавляется отдельно
            if category_name.lower() == "все двери":
                continue
                
            category_id = category_data.get('id')
            if not category_id:
                continue
            
            # Получаем ключевые слова
            keywords = category_data.get('keywords', [])
            
            # Проверяем вхождение ключевых слов
            matches = 0
            for keyword in keywords:
                if keyword.lower() in text_to_analyze:
                    matches += 1
                    # Если есть бонус для этой категории от бренда
                    if category_name.lower() in brand_boosts:
                        matches += brand_boosts[category_name.lower()]
            
            # Если есть хотя бы одно совпадение, добавляем категорию
            if matches > 0:
                category_ids.add(category_id)
                self.logger.info(f"Продукт ID:{product_id} добавлен в категорию '{category_name}' (найдено {matches} совпадений)")
        
        return category_ids
    
    async def add_product_to_categories(self, db: AsyncSession, product_id: int, category_ids: Set[int]) -> None:
        """Добавляет продукт в указанные категории"""
        if not category_ids:
            self.logger.warning(f"Для продукта ID:{product_id} не найдено подходящих категорий")
            return
        
        product_exists = await db.execute(
            select(Product.id).where(Product.id == product_id)
        )
        
        if not product_exists.scalar_one_or_none():
            self.logger.warning(f"Продукт с ID:{product_id} не существует в базе данных")
            return
        
        # Удаляем существующие связи
        stmt = delete(product_categories).where(product_categories.c.product_id == product_id)
        await db.execute(stmt)
        
        # Выбираем первую категорию как основную
        primary_category_id = next(iter(category_ids))
        
        # Добавляем новые связи
        for category_id in category_ids:
            values = {
                'product_id': product_id,
                'category_id': category_id
            }
            
            # Если таблица поддерживает флаг is_primary
            if hasattr(product_categories.c, 'is_primary'):
                values['is_primary'] = (category_id == primary_category_id)
                
            stmt = insert(product_categories).values(**values)
            await db.execute(stmt)
    
    async def classify_and_update_product(self, db: AsyncSession, product_id: int, text_to_analyze: str, category_map: Dict[str, Dict]) -> None:
        """Классифицирует продукт и обновляет его категории"""
        category_ids = await self.classify_product(db, product_id, text_to_analyze, category_map)
        
        if category_ids:
            await self.add_product_to_categories(db, product_id, category_ids)
    
    async def update_category_counters(self, db: AsyncSession) -> None:
        """Обновляет счетчики товаров для всех категорий"""
        self.logger.info("Обновление счетчиков товаров в категориях...")
        
        # Получаем все категории
        result = await db.execute(select(Category))
        categories = result.scalars().all()
        
        for category in categories:
            # Подсчитываем количество товаров в категории
            count_query = select(func.count()).select_from(product_categories).where(
                product_categories.c.category_id == category.id
            )
            result = await db.execute(count_query)
            count = result.scalar_one()
            
            # Обновляем поле product_count, если оно существует
            if hasattr(Category, 'product_count'):
                category.product_count = count
                db.add(category)
                await db.flush()
                self.logger.info(f"Категория '{category.name}': обновлено количество товаров - {count}")
            else:
                self.logger.warning(f"Поле 'product_count' отсутствует в модели Category")
        
        # Коммитим изменения
        await db.commit()
        self.logger.info("Счетчики товаров в категориях обновлены")


    async def ensure_products_in_default_category(self, db: AsyncSession, brand_id: int) -> None:
        """
        Проверяет, что все товары бренда находятся в категории 'все двери'
        и добавляет их туда, если нет
        """
        # Получаем категорию "все двери"
        default_category = await self.get_or_create_default_category(db, brand_id)
        default_category_id = default_category.id
        
        # Получаем все товары бренда
        products_result = await db.execute(
            select(Product).where(Product.brand_id == brand_id)
        )
        products = products_result.scalars().all()
        
        # Проверяем для каждого товара
        added_count = 0
        for product in products:
            # Проверяем, есть ли товар в категории "все двери"
            result = await db.execute(
                select(func.count()).select_from(product_categories).where(
                    product_categories.c.product_id == product.id,
                    product_categories.c.category_id == default_category_id
                )
            )
            count = result.scalar_one()
            
            # Если товара нет в категории "все двери", добавляем
            if count == 0:
                values = {
                    'product_id': product.id,
                    'category_id': default_category_id
                }
                
                # Если таблица поддерживает флаг is_primary
                if hasattr(product_categories.c, 'is_primary'):
                    values['is_primary'] = True
                    
                stmt = insert(product_categories).values(**values)
                await db.execute(stmt)
                added_count += 1
        
        if added_count > 0:
            await db.flush()
            self.logger.info(f"Добавлено {added_count} товаров в категорию 'все двери'")
    
    # ---------- Основной метод парсинга ----------
    
    async def parse_multiple_catalogs(self, catalog_urls: List[str], db: AsyncSession) -> int:
        """
        Шаблонный метод для парсинга нескольких каталогов
        Реализация зависит от конкретных скраперов
        """
        raise NotImplementedError("Этот метод должен быть переопределен в дочернем классе")