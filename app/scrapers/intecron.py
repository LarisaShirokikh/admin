"""
Скрапер для сайта Intecron
"""
from typing import List, Dict, Any, Optional, Set
import logging
import json
import time
import re
from bs4 import BeautifulSoup
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.schemas.product import ProductCreate
from app.schemas.product_image import ProductImageCreate
from app.utils.text_utils import generate_slug, clean_text
from app.crud.product import create_or_update_product
from app.scrapers.base_scraper import BaseScraper

logger = logging.getLogger("intecron_scraper")

class IntecronScraper(BaseScraper):
    def __init__(self):
        super().__init__(
            brand_name="Интекрон",
            brand_slug="intecron",
            base_url="https://intecron-msk.ru",
            logger_name="intecron_scraper"
        )
        
        # Специфичные паттерны для исключения изображений
        self.image_exclude_patterns = [
            "logo", "brand", "header", "footer", "banner", "menu", "icon", "button", 
            "small", "mini", "thumb", "iblock", "bitrix", "templates", "intecron", 
            "ico", "svg", "favicon", "min", "ywkciutsl8t3v8b1kv1rw2zlb5s02xqy", 
            "qakcfj3fwhgp68nn1brewvwaxysuarfp"  # Конкретные заглушки Intecron
        ]
        
    def is_valid_image_url(self, img_src: str) -> bool:
        """
        Проверяет, является ли URL валидным изображением продукта
        """
        if not img_src:
            return False
            
        # Интерон часто использует URL типа /upload/iblock/...
        if '/upload/iblock/' in img_src and any(ext in img_src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
            return True
            
        # Общие проверки для других форматов URL
        if not any(pattern in img_src.lower() for pattern in self.image_exclude_patterns):
            if (len(img_src) > 20 and 
            ('.jpg' in img_src.lower() or '.jpeg' in img_src.lower() or 
                '.png' in img_src.lower() or '.webp' in img_src.lower())):
                return True
        
        return False

    def add_image_url_if_valid(self, image_urls: List[str], raw_url: str) -> bool:
        """
        Добавляет URL изображения в список, если он валиден
        Возвращает True, если изображение было добавлено
        """
        if not raw_url:
            return False

        # Проверяем, является ли URL абсолютным
        full_url = raw_url
        if not raw_url.startswith('http'):
            # Удаляем начальный слеш, если он есть
            clean_url = raw_url.lstrip('/')
            full_url = f"{self.base_url}/{clean_url}"

        # Проверяем валидность изображения
        if not self.is_valid_image_url(full_url):
            return False

        # Проверяем дубликаты
        if full_url in image_urls:
            return False

        # Добавляем URL в список
        image_urls.append(full_url)
        self.logger.debug(f"Добавлено изображение: {full_url}")
        return True
    
    async def find_product_links(self, soup: BeautifulSoup) -> List[str]:
        """
        Находит все ссылки на товары на странице каталога
        """
        product_links = []
        
        # Ищем ссылки в разных типах элементов
        link_selectors = [
            "a.btn-wht",
            "a.btn",
            "a.product-link",
            "a.detail-link",
            "a[href*='/catalog/'][href*='detail']",
            ".pr-bl a[href]",
            ".catalog-item a[href]",
            ".product-item a[href]"
        ]
        
        for selector in link_selectors:
            for a in soup.select(selector):
                href = a.get('href')
                if href and ('/catalog/' in href or '/product/' in href):
                    # Исключаем категории и другие нетоварные ссылки
                    if href.count('/') > 2 and not href.endswith('/'):
                        product_links.append(href)
        
        # Если не нашли ссылки с предыдущими селекторами, ищем по контексту
        if not product_links:
            # Ищем ссылки с кнопками "Подробнее", "В корзину" и т.д.
            for a in soup.find_all('a', href=True):
                href = a.get('href')
                text = a.get_text().lower()
                if (href and ('/catalog/' in href or '/product/' in href) and 
                    ('подробнее' in text or 'корзину' in text or 'detail' in href or 'product' in href)):
                    product_links.append(href)
        
        # Удаляем дубликаты, сохраняя порядок
        unique_links = []
        seen = set()
        for link in product_links:
            if link not in seen:
                seen.add(link)
                unique_links.append(link)
        
        self.logger.info(f"Найдено {len(unique_links)} уникальных ссылок на товары")
        return unique_links
    
    async def process_product_page(self, product_url: str, catalog_name: str, brand_id: int, catalog_id: int = None) -> Optional[ProductCreate]:
        """
        Обрабатывает страницу товара и создает объект ProductCreate
        """
        # Формируем полный URL
        product_url = self.normalize_url(product_url)
        
        self.logger.info(f"Обработка товара по URL: {product_url}")
        
        # Проверяем, что catalog_id не None
        if catalog_id is None:
            self.logger.error(f"catalog_id не может быть None для товара: {product_url}")
            return None
        
        # Получаем HTML с поддержкой ленивой загрузки изображений
        html_content = self.get_html_content(product_url)
        if not html_content:
            self.logger.warning(f"Не удалось получить HTML-страницу товара: {product_url}")
            return None
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Извлекаем название товара
        name_selectors = ["h1", ".page-title", ".product-item-title", ".h4", ".name", ".title"]
        name = None
        for selector in name_selectors:
            name_elem = soup.select_one(selector)
            if name_elem and name_elem.text.strip():
                name = name_elem.text.strip()
                break
        
        if not name:
            self.logger.warning(f"Не удалось найти название товара: {product_url}")
            return None
        
        # Извлекаем цену
        price = 0
        price_selectors = [".price", ".product-item-price-current", ".catalog-price", "[class*='price']"]
        for selector in price_selectors:
            price_elems = soup.select(selector)
            for price_elem in price_elems:
                price_text = price_elem.text.strip()
                extracted_price = self.extract_price_from_text(price_text)
                if extracted_price > price:
                    price = extracted_price
        
        # Извлекаем описание
        description_parts = []
        description_selectors = [
            ".product-item-detail-tab-content", 
            ".product-item-detail-properties",
            ".detail_text",
            ".product-description",
            ".desc",
            ".details"
        ]
        
        for selector in description_selectors:
            desc_elems = soup.select(selector)
            for elem in desc_elems:
                description_parts.append(clean_text(elem.get_text()))
        
        # Если описание не найдено, создаем базовое описание
        if not description_parts:
            description = f"Дверь {name} от производителя Intecron. Качественная металлическая дверь с надежной защитой."
        else:
            description = " ".join(description_parts)
        
        # Извлекаем характеристики
        characteristics = {}
        specs_selectors = [
            ".product-item-detail-properties tr",
            ".properties tr",
            ".specs tr",
            ".characteristics tr",
            "table tr"
        ]
        
        for selector in specs_selectors:
            specs = soup.select(selector)
            for spec in specs:
                cells = spec.find_all(['td', 'th'])
                if len(cells) >= 2:
                    key = clean_text(cells[0].get_text())
                    value = clean_text(cells[1].get_text())
                    if key and value and len(key) < 100:
                        characteristics[key] = value
        
        # Получаем изображения
        image_urls = self.extract_product_images(soup, product_url)
        
        if not image_urls:
            self.logger.warning(f"Не найдено ни одного изображения для товара: {name} ({product_url})")
            # Добавляем заглушку-изображение, если не найдено ни одного
            image_urls = ["https://intecron-msk.ru/local/templates/intecron_new/img/no-photo.jpg"]
        
        # Создаем объекты для изображений
        images = [ProductImageCreate(url=img, is_main=(i == 0)) for i, img in enumerate(image_urls)]
        
        # Генерируем slug
        product_slug = generate_slug(name)
        
        # Создаем мета-описание
        meta_description = self.create_meta_description(description, characteristics)
        
        # Создаем продукт - НЕ передаем catalog_name в ProductCreate
        product = ProductCreate(
            name=name,
            price=price,
            description=description,
            catalog_id=catalog_id,  # Только catalog_id
            # Убираем catalog_name, он не нужен для модели Product
            images=images,
            image=image_urls[0] if image_urls else None,
            in_stock=True,
            characteristics=characteristics,
            slug=product_slug,
            meta_title=f"{name} - Intecron",
            meta_description=meta_description[:500],
            brand_id=brand_id
        )
        
        self.logger.info(f"Успешно создан продукт: {name} с {len(images)} изображениями, catalog_id: {catalog_id}")
        return product
    
    # Обновленные селекторы для извлечения изображений
    def extract_product_images(self, soup: BeautifulSoup, product_url: str) -> List[str]:
        """
        Извлекает только качественные изображения продукта
        """
        # Сначала собираем все возможные изображения
        all_image_urls = []
        valid_image_urls = []
        
        # Базовые селекторы для основных изображений
        basic_selectors = [
            ".swiper-slide a img",
            ".magnific_popup_mobile img",
            ".product-detail-slider-image img",
            "[data-entity='image'] img"
        ]
        
        # Сначала ищем по нашим основным селекторам
        for selector in basic_selectors:
            for img in soup.select(selector):
                src = img.get('src')
                if src:
                    all_image_urls.append(self.normalize_url(src))
        
        # Ищем в data-атрибутах
        for elem in soup.find_all(attrs={"data-entity": "images-container"}):
            for img_elem in elem.find_all('img'):
                src = img_elem.get('src')
                if src:
                    all_image_urls.append(self.normalize_url(src))
        
        # Извлекаем из data-value (специфично для Intecron)
        for elem in soup.find_all(attrs={"data-value": True}):
            data_value = elem.get('data-value')
            if data_value and '"SRC":"' in data_value:
                img_matches = re.findall(r'"SRC":"([^"]+)"', data_value)
                for img_match in img_matches:
                    img_url = img_match.replace('\/', '/')
                    all_image_urls.append(self.normalize_url(img_url))
        
        # Фильтруем и добавляем только валидные
        seen_urls = set()
        for url in all_image_urls:
            # Проверяем основные критерии для продуктовых изображений
            if self.is_valid_product_image(url) and url not in seen_urls:
                seen_urls.add(url)
                valid_image_urls.append(url)
                # Ограничиваем до 5 изображений
                if len(valid_image_urls) >= 5:
                    break
        
        # Если не нашли ни одного изображения, используем резервные методы
        if not valid_image_urls:
            # Последняя попытка - ищем все изображения с минимальной фильтрацией
            for img in soup.find_all('img'):
                src = img.get('src')
                if src and '/upload/' in src and src.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    url = self.normalize_url(src)
                    if url not in seen_urls:
                        seen_urls.add(url)
                        valid_image_urls.append(url)
                        # Берем только 2 изображения в резервном режиме
                        if len(valid_image_urls) >= 2:
                            break
        
        self.logger.info(f"Найдено {len(valid_image_urls)} валидных изображений для продукта {product_url}")
        return valid_image_urls

    def is_valid_product_image(self, url: str) -> bool:
        """
        Проверяет, является ли URL качественным изображением продукта
        """
        # Основные критерии для продуктовых изображений
        if not url:
            return False
        
        # Проверяем расширение
        if not url.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
            return False
        
        # Проверяем, что URL содержит /upload/ или /iblock/ (типично для Bitrix)
        if '/upload/' not in url and '/iblock/' not in url:
            return False
        
        # Исключаем миниатюры и системные изображения
        excluded_patterns = [
            'logo', 'icon', 'button', 'banner', 'menu', 'min', 'small', 'thumb',
            'background', 'bg_', 'header', 'footer'
        ]
        
        for pattern in excluded_patterns:
            if pattern in url.lower():
                return False
        
        return True
        
    def normalize_url(self, url: str) -> str:
        """
        Преобразует относительный URL в абсолютный
        """
        if not url:
            return ""
            
        # Если URL уже абсолютный, возвращаем как есть
        if url.startswith(('http://', 'https://')):
            return url
            
        # Удаляем начальный слеш, если он есть
        clean_url = url.lstrip('/')
        
        # Формируем полный URL
        full_url = f"{self.base_url}/{clean_url}"
        
        # Исправляем двойные слеши (кроме https://)
        full_url = re.sub(r'([^:])//+', r'\1/', full_url)
        
        return full_url
    
    async def parse_catalog_page(self, catalog_url: str, db: AsyncSession, brand_id: int) -> List[ProductCreate]:
        """
        Парсит страницу каталога Intecron и возвращает список объектов ProductCreate
        """
        # Формируем полный URL
        catalog_url = self.normalize_url(catalog_url)
        
        # Обновляем URL для корректного домена
        if "intecron.ru" in catalog_url:
            catalog_url = catalog_url.replace("intecron.ru", "intecron-msk.ru")
        
        self.logger.info(f"Парсинг каталога: {catalog_url}")
        
        # Получаем HTML страницы
        html_content = self.get_html_content(catalog_url)
        if not html_content:
            self.logger.error(f"Не удалось получить HTML-страницу каталога: {catalog_url}")
            return []
        
        # Определяем имя и slug каталога из URL
        catalog_parts = catalog_url.rstrip('/').split('/')
        catalog_slug = catalog_parts[-1]
        if not catalog_slug:
            catalog_slug = catalog_parts[-2]
        
        # Формируем имя каталога
        catalog_name_part = catalog_slug.replace('-', ' ').title()
        catalog_name = f"Двери Intecron {catalog_name_part}"
        
        # Получаем или создаем каталог (правильный порядок аргументов: db, name, slug, brand_id)
        catalog = await self.get_or_create_catalog(db, catalog_name, catalog_slug, brand_id)
        
        if not catalog:
            self.logger.error(f"Не удалось создать каталог {catalog_name}")
            return []
        
        # Убедимся, что catalog.id не None
        if catalog.id is None:
            self.logger.error(f"catalog.id не может быть None для каталога {catalog_name}")
            return []
        
        catalog_id = catalog.id
        self.logger.info(f"Каталог получен с ID: {catalog_id}")
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Находим ссылки на товары
        product_links = await self.find_product_links(soup)
        
        # Если нет ссылок на товары, возвращаем пустой список
        if not product_links:
            self.logger.warning(f"Не найдено ссылок на товары в каталоге: {catalog_url}")
            return []
        
        # Обрабатываем каждую ссылку на товар
        products = []
        catalog_image_updated = False
        
        for link in product_links:
            try:
                # Передаем catalog_id в метод process_product_page
                # Явно логируем передаваемые параметры
                self.logger.info(f"Вызов process_product_page для {link} с catalog_id={catalog_id}")
                product = await self.process_product_page(link, catalog_name, brand_id, catalog_id)
                
                if product:
                    # Проверяем, что у продукта установлен catalog_id
                    self.logger.info(f"Получен продукт с catalog_id: {product.catalog_id}")
                    products.append(product)
                    
                    # Обновляем изображение каталога, если это первый продукт с изображениями
                    if not catalog_image_updated and product.images and product.images[0].url:
                        await self.update_catalog_image(db, catalog, product.images[0].url)
                        catalog_image_updated = True
            except Exception as e:
                self.logger.error(f"Ошибка при обработке товара по ссылке {link}: {e}", exc_info=True)
        
        self.logger.info(f"Всего обработано {len(products)} товаров из каталога {catalog_url}")
        return products
    
    async def parse_multiple_catalogs(self, catalog_urls: List[str], db: AsyncSession) -> int:
        """
        Парсит несколько каталогов и создает или обновляет продукты в базе данных
        с автоматической категоризацией
        """
        self.logger.info(f"Запуск парсера для {len(catalog_urls)} каталогов")
        total_products = 0
        new_products = 0
        updated_products = 0
        
        # Получаем или создаем бренд Intecron
        brand_id = await self.ensure_brand_exists(db)
        self.logger.info(f"Получен ID бренда Intecron: {brand_id}")
        
        # Обновляем существующие каталоги, чтобы привязать их к бренду
        await self.update_catalogs_brand_id(db, brand_id)
        
        # Получаем или создаем категорию "все двери"
        all_doors_category = await self.get_or_create_default_category(db, brand_id)
        all_doors_category_id = all_doors_category.id
        
        # Собираем продукты для последующей классификации
        products_to_classify = []
        
        for url in catalog_urls:
            try:
                products = await self.parse_catalog_page(url, db, brand_id)
                self.logger.info(f"Получено {len(products)} продуктов из каталога {url}")
                
                for product_in in products:
                    try:
                        # Проверка на существование продукта перед созданием нового
                        result = await db.execute(
                            select(Product).where(
                                or_(
                                    Product.slug == product_in.slug,
                                    func.lower(Product.name) == product_in.name.lower()
                                )
                            )
                        )
                        existing_product = result.scalar_one_or_none()
                        
                        # Создаем или обновляем продукт
                        created_product = await create_or_update_product(db, product_in)
                        
                        if created_product:
                            # Сразу добавляем товар в категорию "все двери"
                            await self.add_product_to_category(db, created_product.id, all_doors_category_id)
                            
                            # Собираем текст для дополнительной классификации
                            text_to_analyze = f"{product_in.name} {product_in.description}"
                            
                            # Добавляем характеристики продукта в текст для анализа
                            if product_in.characteristics:
                                for key, value in product_in.characteristics.items():
                                    text_to_analyze += f" {key} {value}"
                            
                            # Добавляем в список для дополнительной классификации
                            products_to_classify.append((created_product.id, text_to_analyze))
                            
                            # Увеличиваем счетчики
                            total_products += 1
                            if existing_product:
                                updated_products += 1
                            else:
                                new_products += 1
                                
                            await db.flush()
                        else:
                            self.logger.warning(f"Не удалось создать/обновить продукт {product_in.name}")
                    
                    except Exception as e:
                        # Если произошла ошибка при обработке конкретного товара, логируем и продолжаем
                        self.logger.warning(f"[SCRAPER] Ошибка при обработке товара: {e}")
                        # Делаем rollback сессии
                        await db.rollback()
            
            except Exception as e:
                self.logger.error(f"[SCRAPER] Ошибка при обработке каталога {url}: {e}", exc_info=True)
                # Делаем rollback чтобы избежать накопления ошибок
                await db.rollback()

        # Делаем коммит всех созданных/обновленных продуктов перед дополнительной классификацией
        try:
            await db.commit()
            self.logger.info(f"Успешно обработано {total_products} продуктов (новых: {new_products}, обновлено: {updated_products})")
        except Exception as e:
            self.logger.error(f"[SCRAPER] Ошибка при сохранении продуктов: {e}", exc_info=True)
            await db.rollback()
            return 0

        # Дополнительно классифицируем продукты по другим категориям
        if products_to_classify:
            try:
                # Используем уже полученный brand_id вместо повторного вызова ensure_brand_exists
                await self.ensure_categories_exist(db, brand_id)
                category_map = await self.get_category_map(db)
                
                # Классифицируем продукты (добавляем в дополнительные категории)
                for product_id, text_to_analyze in products_to_classify:
                    await self.classify_product_additional_categories(db, product_id, text_to_analyze, category_map)
                
                # Коммитим все изменения по классификации
                await db.commit()
                
                # Обновляем счетчики товаров в категориях
                await self.update_category_counters(db)
                
            except Exception as e:
                self.logger.error(f"[SCRAPER] Ошибка при классификации продуктов: {e}", exc_info=True)
                # Ошибка классификации не должна блокировать успешное добавление продуктов
                await db.rollback()

        self.logger.info(f"Создано и обновлено {total_products} товаров (новых: {new_products}, обновлено: {updated_products})")
        return total_products