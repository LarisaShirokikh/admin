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

from app.scrapers.door_synonyms import DOOR_PATTERNS, DOOR_SYNONYMS, MORPHOLOGY_VARIANTS
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

        # Кэш для категорий и их ключевых слов
        self._categories_cache = None
        self._category_patterns_cache = None
        
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

    async def verify_catalog_exists(self, db: AsyncSession, catalog_id: int) -> bool:
        """
        Проверяет, что каталог с указанным ID существует в базе данных
        
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
    def _prepare_product_text_for_analysis(self, product_in: ProductCreate) -> str:
        """
        УНИВЕРСАЛЬНАЯ ВЕРСИЯ: Подготавливает текст продукта для анализа категорий
        Работает для всех скраперов
        """
        text_parts = []
        
        # Название продукта (самый важный текст)
        if hasattr(product_in, 'name') and product_in.name:
            text_parts.append(product_in.name)
        
        # Описание
        if hasattr(product_in, 'description') and product_in.description:
            text_parts.append(product_in.description)
        
        # Характеристики (если они есть как отдельное поле)
        if hasattr(product_in, 'characteristics') and product_in.characteristics:
            if isinstance(product_in.characteristics, dict):
                for key, value in product_in.characteristics.items():
                    if key and value:  # Проверяем, что не пустые
                        text_parts.append(f"{key} {value}")
            elif isinstance(product_in.characteristics, str):
                text_parts.append(product_in.characteristics)
        
        # Мета-информация
        if hasattr(product_in, 'meta_title') and product_in.meta_title:
            text_parts.append(product_in.meta_title)
        
        if hasattr(product_in, 'meta_description') and product_in.meta_description:
            text_parts.append(product_in.meta_description)
        
        # Артикул (если есть)
        if hasattr(product_in, 'article') and product_in.article:
            text_parts.append(product_in.article)
        
        # Объединяем все части
        result = " ".join(text_parts)
        
        # Отладочное логирование
        if hasattr(self, 'logger'):
            self.logger.debug(f"Подготовлен текст для анализа ({len(result)} символов): {result[:100]}...")
        
        return result

    async def get_all_categories_from_db(self, db: AsyncSession) -> Dict[str, Dict]:
        """
        УЛУЧШЕНО: Получает все активные категории из базы данных с кэшированием
        """
        if self._categories_cache is not None:
            return self._categories_cache
        
        result = await db.execute(
            select(Category).where(Category.is_active == True)
        )
        categories = result.scalars().all()
        
        category_map = {}
        for category in categories:
            # Генерируем ключевые слова из названия категории и её атрибутов
            keywords, patterns = self._generate_enhanced_category_keywords(category)
            
            category_map[category.name.lower()] = {
                'id': category.id,
                'name': category.name,
                'slug': category.slug,
                'keywords': keywords,
                'patterns': patterns,
                'is_default': self._is_default_category(category.name)
            }
        
        # Кэшируем результат
        self._categories_cache = category_map
        
        self.logger.info(f"Загружено {len(category_map)} категорий для классификации")
        
        # Логируем категории для отладки
        for name, data in category_map.items():
            keywords_preview = data['keywords'][:3] if len(data['keywords']) > 3 else data['keywords']
            self.logger.debug(f"Категория '{name}': keywords={keywords_preview}...")
        
        return category_map
    
    def _generate_enhanced_category_keywords(self, category: Category) -> Tuple[List[str], List[str]]:
        """ генерация ключевых слов и паттернов для категории"""
        keywords = set()
        patterns = []
        
        # Добавляем само название категории
        category_name_lower = category.name.lower()
        keywords.add(category_name_lower)
        
        # Разбиваем название на отдельные слова
        name_words = category_name_lower.split()
        keywords.update(name_words)
        
        # Добавляем slug (если есть)
        if hasattr(category, 'slug') and category.slug:
            slug_words = category.slug.replace('-', ' ').split()
            keywords.update(slug_words)
        
        # Добавляем мета-ключевые слова (если есть)
        if hasattr(category, 'meta_keywords') and category.meta_keywords:
            meta_words = [kw.strip().lower() for kw in category.meta_keywords.split(',')]
            keywords.update(meta_words)
        
        # НОВОЕ: Специальные правила с морфологией и синонимами
        category_synonyms = self._get_category_synonyms(category_name_lower)
        keywords.update(category_synonyms)
        
        # НОВОЕ: Генерируем паттерны для более гибкого поиска
        category_patterns = self._generate_category_patterns(category_name_lower)
        patterns.extend(category_patterns)
        
        # Убираем пустые строки и очень короткие слова
        keywords = {kw for kw in keywords if kw and len(kw) > 1}
        
        return list(keywords), patterns
    
    def _get_category_synonyms(self, category_name: str) -> Set[str]:
        """
        НОВОЕ: Получает синонимы и морфологические варианты для категории
        """
        synonyms = set()
        
        # Добавляем синонимы для найденных слов
        for word in category_name.split():
            word_lower = word.lower()
            if word_lower in DOOR_SYNONYMS:
                synonyms.update(DOOR_SYNONYMS[word_lower])
        
        # Также проверяем полное название категории
        category_lower = category_name.lower()
        if category_lower in DOOR_SYNONYMS:
            synonyms.update(DOOR_SYNONYMS[category_lower])
        
        # Добавляем морфологические варианты
        for word in category_name.split():
            word_lower = word.lower()
            if word_lower in MORPHOLOGY_VARIANTS:
                synonyms.update(MORPHOLOGY_VARIANTS[word_lower])
        
        return synonyms
    
    def _generate_category_patterns(self, category_name: str) -> List[str]:
        """
        НОВОЕ: Генерирует регулярные выражения для более гибкого поиска
        """
        patterns = []
        
        # Паттерн для поиска слов с возможными окончаниями
        words = category_name.split()
        
        for word in words:
            if len(word) >= 4:  # Только для слов длиннее 3 символов
                # Создаем паттерн, который ищет корень слова + любые окончания
                root = word[:len(word)-2]  # Берем корень без последних 2 символов
                pattern = rf'\b{re.escape(root)}\w*\b'
                patterns.append(pattern)
        
        # Добавляем специальные паттерны, если они подходят к категории
        category_lower = category_name.lower()
        for key, patterns_list in DOOR_PATTERNS.items():
            if key in category_lower:
                patterns.extend(patterns_list)
        
        # Дополнительно проверяем отдельные слова категории
        for word in words:
            word_lower = word.lower()
            for key, patterns_list in DOOR_PATTERNS.items():
                if key in word_lower or word_lower.startswith(key[:4]):
                    patterns.extend(patterns_list)
                    break
        
        return patterns
    
    def _is_default_category(self, category_name: str) -> bool:
        """Определяет, является ли категория категорией по умолчанию """
        default_names = ['все двери', 'все товары', 'общие', 'основные', 'default']
        return any(default in category_name.lower() for default in default_names)
    
    async def get_default_category(self, db: AsyncSession) -> Optional[Category]:
        """
        Получает общую категорию "Все двери" 
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
                                           min_matches: int = 1,
                                           debug_product_name: str = "") -> List[Dict]:
        """
        УЛУЧШЕНО: Классифицирует продукт по категориям с улучшенным алгоритмом
        """
        # Нормализуем текст для лучшего поиска
        normalized_text = self.normalize_text_for_classification(product_text)
        
        self.logger.debug(f"=== КЛАССИФИКАЦИЯ ПРОДУКТА: {debug_product_name} ===")
        self.logger.debug(f"Нормализованный текст (первые 200 символов): {normalized_text[:200]}...")
        
        matched_categories = []
        
        for category_name, category_data in all_categories.items():
            # Пропускаем категорию "все двери" - она обрабатывается отдельно
            if category_data.get('is_default', False):
                continue
            
            keywords = category_data.get('keywords', [])
            patterns = category_data.get('patterns', [])
            
            if not keywords and not patterns:
                continue
            
            matches = 0
            matched_keywords = []
            matched_patterns = []
            total_weight = 0
            
            # Ищем совпадения по ключевым словам
            for keyword in keywords:
                if keyword in normalized_text:
                    matches += 1
                    matched_keywords.append(keyword)
                    
                    # Вес зависит от длины ключевого слова
                    word_weight = len(keyword.split()) * 1.0
                    
                    # Бонус за точное совпадение фразы
                    if len(keyword.split()) > 1:
                        word_weight *= 1.5
                    
                    # Бонус за точное совпадение названия категории
                    if keyword == category_name:
                        word_weight *= 2.0
                    
                    total_weight += word_weight
            
            # НОВОЕ: Ищем совпадения по регулярным выражениям
            for pattern in patterns:
                try:
                    matches_found = re.findall(pattern, normalized_text, re.IGNORECASE)
                    if matches_found:
                        matches += len(matches_found)
                        matched_patterns.extend(matches_found)
                        # Паттерны получают больший вес
                        total_weight += len(matches_found) * 1.5
                except re.error:
                    self.logger.warning(f"Некорректный регулярный паттерн: {pattern}")
            
            # Если достаточно совпадений, добавляем категорию
            if matches >= min_matches:
                matched_categories.append({
                    'id': category_data['id'],
                    'name': category_data['name'],
                    'slug': category_data['slug'],
                    'weight': total_weight,
                    'matches': matches,
                    'matched_keywords': matched_keywords,
                    'matched_patterns': matched_patterns
                })
                
                self.logger.debug(
                    f"Найдена категория '{category_data['name']}': "
                    f"вес={total_weight:.2f}, совпадений={matches}, "
                    f"ключевые слова={matched_keywords}, "
                    f"паттерны={matched_patterns}"
                )
        
        # Сортируем по весу (по убыванию)
        matched_categories.sort(key=lambda x: x['weight'], reverse=True)
        
        self.logger.info(
            f"Классификация завершена для '{debug_product_name}': "
            f"найдено {len(matched_categories)} подходящих категорий"
        )
        
        if not matched_categories:
            self.logger.warning(
                f"Продукт '{debug_product_name}' не классифицирован ни в одну категорию. "
                f"Текст: {normalized_text[:100]}..."
            )
        else:
            # Показываем топ-3 категории
            top_categories = matched_categories[:3]
            for i, cat in enumerate(top_categories, 1):
                self.logger.info(
                    f"  {i}. {cat['name']} (вес: {cat['weight']:.2f}, "
                    f"совпадений: {cat['matches']})"
                )
        
        return matched_categories
    
    async def assign_product_to_all_categories(self, 
                                         db: AsyncSession, 
                                         product_id: int,
                                         default_category_id: int,
                                         additional_categories: List[Dict],
                                         max_additional_categories: int = 5) -> None:
        """
        УЛУЧШЕНО: Назначает продукт в категории с ограничением количества
        """
        # Удаляем все существующие связи продукта с категориями
        stmt = delete(product_categories).where(product_categories.c.product_id == product_id)
        await db.execute(stmt)
        
        assigned_categories = []
        
        # 1. ОБЯЗАТЕЛЬНО добавляем в категорию "Все двери"
        await self.add_product_to_category(db, product_id, default_category_id, is_primary=True)
        assigned_categories.append(default_category_id)
        
        self.logger.info(f"Продукт {product_id} добавлен в основную категорию 'Все двери' (ID: {default_category_id})")
        
        # 2. Добавляем в дополнительные категории (ограничиваем количество)
        categories_to_add = additional_categories[:max_additional_categories]
        
        for category_info in categories_to_add:
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
                f"(вес: {category_info['weight']:.2f}, совпадений: {category_info['matches']})"
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

    def normalize_text_for_classification(self, text: str) -> str:
        """
        НОВОЕ: Нормализует текст для лучшего сопоставления с категориями
        """
        if not text:
            return ""
        
        # Приводим к нижнему регистру
        normalized = text.lower()
        
        # Удаляем лишние пробелы и переносы строк
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Заменяем некоторые символы для лучшего поиска
        replacements = {
            'ё': 'е',
            '—': '-',
            '–': '-',
            '"': '"',
            '"': '"',
            ''': "'",
            ''': "'",
        }
        
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        
        return normalized.strip()
    
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
    
    # ---------- МЕТОДЫ ДИАГНОСТИКИ ----------
    
    async def diagnose_categorization_issues(self, db: AsyncSession, sample_products: List[Dict]) -> None:
        """
        НОВОЕ: Диагностирует проблемы с категоризацией на примере продуктов
        
        Args:
            db: Сессия базы данных  
            sample_products: Список продуктов для диагностики
                            [{'name': str, 'description': str}, ...]
        """
        self.logger.info("=== ДИАГНОСТИКА СИСТЕМЫ КАТЕГОРИЗАЦИИ ===")
        
        # Загружаем категории
        all_categories = await self.get_all_categories_from_db(db)
        default_category = await self.get_default_category(db)
        
        self.logger.info(f"Всего категорий: {len(all_categories)}")
        self.logger.info(f"Категория по умолчанию: {default_category.name if default_category else 'НЕ НАЙДЕНА'}")
        
        # Анализируем каждый продукт
        total_classified = 0
        total_unclassified = 0
        
        for product in sample_products[:10]:  # Ограничиваем до 10 продуктов
            product_text = f"{product.get('name', '')} {product.get('description', '')}"
            
            matched_categories = await self.classify_product_to_categories(
                product_text, 
                all_categories,
                debug_product_name=product.get('name', 'Без названия')
            )
            
            if matched_categories:
                total_classified += 1
            else:
                total_unclassified += 1
        
        # Итоговая статистика
        self.logger.info(f"=== РЕЗУЛЬТАТЫ ДИАГНОСТИКИ ===")
        self.logger.info(f"Классифицировано продуктов: {total_classified}")
        self.logger.info(f"Не классифицировано продуктов: {total_unclassified}")
        
        if total_unclassified > 0:
            self.logger.warning("Обнаружены проблемы с категоризацией!")
            self.logger.warning("Рекомендации:")
            self.logger.warning("1. Проверьте ключевые слова категорий")
            self.logger.warning("2. Добавьте больше синонимов")
            self.logger.warning("3. Улучшите описания продуктов")