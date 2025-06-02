"""
Базовый модуль с общими компонентами для всех скраперов
Работает только с существующими категориями из БД, не создает новые
"""
import logging
import re
import json
from typing import List, Dict, Any, Optional, Set, Tuple
from bs4 import BeautifulSoup
import requests
from sqlalchemy import func, insert, or_, select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.text_utils import generate_slug
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
    
    # В файле app/scrapers/base_scraper.py исправить метод get_or_create_catalog:

    async def get_or_create_catalog(self, db: AsyncSession, catalog_name: str, catalog_slug: str, brand_id: int) -> Catalog:
        """
        ИСПРАВЛЕНО: Получает или создает каталог с обязательным сохранением в БД
        """
        # Ищем существующий каталог
        result = await db.execute(select(Catalog).where(Catalog.slug == catalog_slug))
        catalog = result.scalar_one_or_none()
        
        if not catalog:
            # Получаем категорию по умолчанию
            default_category = await self.get_default_category(db)
            
            if not default_category:
                self.logger.error("Не найдена категория по умолчанию для создания каталога")
                raise ValueError("Не найдена активная категория для создания каталога")
            
            # Создаем новый каталог
            catalog = Catalog(
                name=catalog_name,
                slug=catalog_slug,
                category_id=default_category.id,
                brand_id=brand_id,
                is_active=True
            )
            db.add(catalog)
            
            # ИСПРАВЛЕНО: Принудительно сохраняем и обновляем
            await db.flush()
            await db.refresh(catalog)
            
            # ИСПРАВЛЕНО: Проверяем что ID установлен
            if catalog.id is None:
                await db.commit()  # Попытка принудительного коммита
                await db.refresh(catalog)
                
            self.logger.info(f"Создан новый каталог: '{catalog_name}' (ID: {catalog.id}, бренд ID: {brand_id})")
            
            # ИСПРАВЛЕНО: Дополнительная проверка существования
            verification_result = await db.execute(select(Catalog).where(Catalog.id == catalog.id))
            verification_catalog = verification_result.scalar_one_or_none()
            
            if not verification_catalog:
                self.logger.error(f"КРИТИЧЕСКАЯ ОШИБКА: Каталог {catalog.id} не найден после создания!")
                raise ValueError(f"Ошибка сохранения каталога {catalog_name}")
                
        else:
            # Проверяем необходимость обновления
            update_needed = False
            
            if catalog.name != catalog_name:
                catalog.name = catalog_name
                update_needed = True
                
            if catalog.brand_id != brand_id:
                catalog.brand_id = brand_id
                update_needed = True
                
            if update_needed:
                db.add(catalog)
                await db.flush()
                await db.refresh(catalog)
                self.logger.info(f"Обновлен каталог: '{catalog_name}' (ID: {catalog.id}, бренд ID: {brand_id})")
        
        return catalog

    # НОВЫЙ МЕТОД: Проверка существования каталога
    async def verify_catalog_exists(self, db: AsyncSession, catalog_id: int) -> bool:
        """
        Проверяет, что каталог с указанным ID существует в базе данных
        
        Args:
            db: Сессия базы данных
            catalog_id: ID каталога
            
        Returns:
            bool: True если каталог существует
        """
        result = await db.execute(select(func.count(Catalog.id)).where(Catalog.id == catalog_id))
        count = result.scalar_one()
        return count > 0
    
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

    # ---------- Динамические методы работы с категориями ----------
    
    async def get_all_categories_from_db(self, db: AsyncSession) -> Dict[str, Dict]:
        """
        Получает все активные категории из базы данных
        Категории общие для всех брендов, бренд устанавливается только для продуктов
        
        Args:
            db: Сессия базы данных
            
        Returns:
            Dict[str, Dict]: Словарь категорий с их данными
        """
        result = await db.execute(
            select(Category).where(Category.is_active == True)
        )
        categories = result.scalars().all()
        
        category_map = {}
        for category in categories:
            # Генерируем ключевые слова из названия категории и её атрибутов
            keywords = self._generate_category_keywords(category)
            
            category_map[category.name.lower()] = {
                'id': category.id,
                'name': category.name,
                'slug': category.slug,
                'keywords': keywords,
                'is_default': self._is_default_category(category.name)
            }
        
        self.logger.info(f"Загружено {len(category_map)} общих категорий для классификации")
        
        # Логируем категории для отладки
        for name, data in category_map.items():
            keywords_preview = data['keywords'][:3] if len(data['keywords']) > 3 else data['keywords']
            self.logger.debug(f"Категория '{name}': keywords={keywords_preview}...")
        
        return category_map
    
    def _generate_category_keywords(self, category: Category) -> List[str]:
        """
        Генерирует ключевые слова для категории на основе её данных
        
        Args:
            category: Объект категории
            
        Returns:
            List[str]: Список ключевых слов
        """
        keywords = set()
        
        # Добавляем само название категории
        keywords.add(category.name.lower())
        
        # Разбиваем название на отдельные слова
        name_words = category.name.lower().split()
        keywords.update(name_words)
        
        # Добавляем slug (если есть)
        if hasattr(category, 'slug') and category.slug:
            slug_words = category.slug.replace('-', ' ').split()
            keywords.update(slug_words)
        
        # Добавляем мета-ключевые слова (если есть)
        if hasattr(category, 'meta_keywords') and category.meta_keywords:
            meta_words = [kw.strip().lower() for kw in category.meta_keywords.split(',')]
            keywords.update(meta_words)
        
        # Специальные правила для разных типов категорий
        category_name_lower = category.name.lower()
        
        if 'металлические' in category_name_lower or 'металлическая' in category_name_lower:
            keywords.update(['металл', 'стальные', 'стальная', 'железные', 'железная'])
        
        if 'входные' in category_name_lower or 'входная' in category_name_lower:
            keywords.update(['уличная', 'наружная', 'внешняя', 'фасадная'])
        
        if 'межкомнатные' in category_name_lower or 'межкомнатная' in category_name_lower:
            keywords.update(['внутренняя', 'комнатная', 'интерьерная'])
        
        if 'деревянные' in category_name_lower or 'деревянная' in category_name_lower:
            keywords.update(['дерево', 'древесина', 'массив', 'шпон'])
        
        if 'стеклянные' in category_name_lower or 'стеклянная' in category_name_lower:
            keywords.update(['стекло', 'остекленные', 'остекленная'])
        
        if 'белые' in category_name_lower or 'белая' in category_name_lower:
            keywords.update(['белый', 'белого цвета', 'светлые', 'светлая'])
        
        if 'черные' in category_name_lower or 'черная' in category_name_lower:
            keywords.update(['черный', 'черного цвета', 'темные', 'темная'])
        
        # Убираем пустые строки и очень короткие слова
        keywords = {kw for kw in keywords if kw and len(kw) > 1}
        
        return list(keywords)
    
    def _is_default_category(self, category_name: str) -> bool:
        """
        Определяет, является ли категория категорией по умолчанию
        
        Args:
            category_name: Название категории
            
        Returns:
            bool: True если это категория по умолчанию
        """
        default_names = ['все двери', 'все товары', 'общие', 'основные', 'default']
        return any(default in category_name.lower() for default in default_names)
    
    async def get_default_category(self, db: AsyncSession) -> Optional[Category]:
        """
        Получает общую категорию "Все двери"
        Категории общие для всех брендов
        
        Args:
            db: Сессия базы данных
            
        Returns:
            Category или None
        """
        # Приоритет 1: Ищем "Все двери"
        result = await db.execute(
            select(Category).where(
                func.lower(Category.name).like('%все двери%'),
                Category.is_active == True
            )
        )
        category = result.scalar_one_or_none()
        if category:
            return category
        
        # Приоритет 2: Ищем любую дефолтную категорию
        result = await db.execute(
            select(Category).where(
                or_(
                    func.lower(Category.name).like('%все товары%'),
                    func.lower(Category.name).like('%общие%'),
                    func.lower(Category.name).like('%основные%'),
                    func.lower(Category.name).like('%default%')
                ),
                Category.is_active == True
            )
        )
        category = result.scalar_one_or_none()
        if category:
            return category
        
        # Приоритет 3: Ищем первую активную категорию
        result = await db.execute(
            select(Category).where(Category.is_active == True).limit(1)
        )
        return result.scalar_one_or_none()
    
    async def classify_product_to_categories(self, 
                                           product_text: str, 
                                           all_categories: Dict[str, Dict],
                                           min_matches: int = 1) -> List[Dict]:
        """
        Классифицирует продукт по категориям на основе текста
        
        Args:
            product_text: Полный текст продукта для анализа
            all_categories: Все доступные категории с ключевыми словами
            min_matches: Минимальное количество совпадений для включения в категорию
            
        Returns:
            List[Dict]: Список подходящих категорий с весами
        """
        text_lower = product_text.lower()
        matched_categories = []
        
        for category_name, category_data in all_categories.items():
            # Пропускаем категорию "все двери" - она обрабатывается отдельно
            if category_data.get('is_default', False):
                continue
            
            keywords = category_data.get('keywords', [])
            if not keywords:
                continue
            
            matches = 0
            matched_keywords = []
            total_weight = 0
            
            for keyword in keywords:
                if keyword in text_lower:
                    matches += 1
                    matched_keywords.append(keyword)
                    
                    # Вес зависит от длины ключевого слова
                    word_weight = len(keyword.split()) * 1.0
                    
                    # Бонус за точное совпадение фразы
                    if len(keyword.split()) > 1:
                        word_weight *= 1.5
                    
                    total_weight += word_weight
            
            # Если достаточно совпадений, добавляем категорию
            if matches >= min_matches:
                matched_categories.append({
                    'id': category_data['id'],
                    'name': category_data['name'],
                    'slug': category_data['slug'],
                    'weight': total_weight,
                    'matches': matches,
                    'matched_keywords': matched_keywords
                })
        
        # Сортируем по весу (по убыванию)
        matched_categories.sort(key=lambda x: x['weight'], reverse=True)
        
        return matched_categories
    
    # Исправление для базового класса BaseScraper

    async def assign_product_to_all_categories(self, 
                                         db: AsyncSession, 
                                         product_id: int,
                                         default_category_id: int,
                                         additional_categories: List[Dict]) -> None:
        """
        ИСПРАВЛЕНО: Назначает продукт в категорию "Все двери" и дополнительные категории
        
        Args:
            db: Сессия базы данных
            product_id: ID продукта
            default_category_id: ID категории "Все двери"
            additional_categories: Дополнительные категории для назначения
        """
        # Удаляем все существующие связи продукта с категориями
        stmt = delete(product_categories).where(product_categories.c.product_id == product_id)
        await db.execute(stmt)
        
        assigned_categories = []
        
        # 1. ОБЯЗАТЕЛЬНО добавляем в категорию "Все двери"
        await self.add_product_to_category(db, product_id, default_category_id, is_primary=True)
        assigned_categories.append(default_category_id)
        
        self.logger.info(f"Продукт {product_id} добавлен в основную категорию 'Все двери' (ID: {default_category_id})")
        
        # 2. Добавляем в дополнительные категории
        for category_info in additional_categories:
            # ИСПРАВЛЕНО: Правильно извлекаем ID из словаря
            category_id = category_info['id']
            category_name = category_info['name']
            
            # Пропускаем, если это та же категория, что и основная
            if category_id == default_category_id:
                continue
            
            # Пропускаем, если уже добавлен
            if category_id in assigned_categories:
                continue
            
            await self.add_product_to_category(db, product_id, category_id, is_primary=False)
            assigned_categories.append(category_id)
            
            self.logger.info(
                f"Продукт {product_id} добавлен в дополнительную категорию '{category_name}' "
                f"(вес: {category_info['weight']:.2f}, совпадений: {category_info['matches']}, "
                f"ключевые слова: {', '.join(category_info['matched_keywords'][:3])})"
            )
        
        await db.flush()
        
        self.logger.info(f"Продукт {product_id} назначен в {len(assigned_categories)} категорий")

    async def clear_product_categories(self, db: AsyncSession, product_id: int) -> None:
        """
        ДОБАВЛЕНО: Очищает все связи продукта с категориями
        """
        stmt = delete(product_categories).where(product_categories.c.product_id == product_id)
        await db.execute(stmt)
        self.logger.debug(f"Очищены все категории для продукта {product_id}")

    # ---------- Основной метод парсинга ----------
    
    async def parse_multiple_catalogs(self, catalog_urls: List[str], db: AsyncSession) -> int:
        """
        Шаблонный метод для парсинга нескольких каталогов
        Реализация зависит от конкретных скраперов
        """
        raise NotImplementedError("Этот метод должен быть переопределен в дочернем классе")
    
    def create_meta_description(self, description: str, characteristics: Dict[str, str] = None) -> str:
        """
        ИСПРАВЛЕНО: Создает мета-описание на основе описания
        (характеристики теперь уже включены в описание)
        """
        if not description:
            return ""
        
        # Берем первую часть описания (до характеристик, если они есть)
        if "\n\nХарактеристики:" in description:
            main_description = description.split("\n\nХарактеристики:")[0]
        else:
            main_description = description
        
        # Ограничиваем длину
        return main_description[:500]