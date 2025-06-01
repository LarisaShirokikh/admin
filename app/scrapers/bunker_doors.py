"""
Исправленный скрапер для сайта Bunker Doors
"""
from typing import List, Dict, Any, Optional
import logging
import json
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

logger = logging.getLogger("bunker_doors_scraper")

class BunkerDoorsScraper(BaseScraper):
    def __init__(self):
        super().__init__(
            brand_name="Bunker Doors",
            brand_slug="bunker-doors",
            base_url="https://bunkerdoors.ru",
            logger_name="bunker_doors_scraper"
        )
    
    def extract_product_links_from_page(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """
        Извлекает ссылки на товары со страницы каталога
        """
        product_links = []
        
        # Ищем товары в списке
        items = soup.select("li.products-list-01-item")
        self.logger.info(f"Найдено {len(items)} товаров на странице")
        
        for i, item in enumerate(items):
            try:
                # Ищем ссылку на товар разными способами
                link_element = None
                
                # Способ 1: Ищем ссылку в изображении товара
                img_link = item.select_one(".products-list-01-item__img a")
                if img_link and img_link.get('href'):
                    link_element = img_link
                    self.logger.info(f"Товар {i+1}: найдена ссылка через изображение")
                
                # Способ 2: Ищем ссылку в заголовке
                if not link_element:
                    title_link = item.select_one(".products-list-01-item__header a")
                    if title_link and title_link.get('href'):
                        link_element = title_link
                        self.logger.info(f"Товар {i+1}: найдена ссылка в заголовке")
                
                # Способ 3: Ищем любую ссылку с href содержащим товарный код
                if not link_element:
                    all_links = item.select("a[href]")
                    for link in all_links:
                        href = link.get('href', '')
                        if any(pattern in href for pattern in ['/bn-', '/fl-', '/prod/']):
                            link_element = link
                            self.logger.info(f"Товар {i+1}: найдена ссылка по паттерну: {href}")
                            break
                
                # Способ 4: Первая ссылка в элементе (если других способов нет)
                if not link_element:
                    first_link = item.select_one("a[href]")
                    if first_link:
                        link_element = first_link
                        self.logger.info(f"Товар {i+1}: используется первая ссылка")
                
                if link_element:
                    href = link_element.get('href')
                    if href:
                        full_url = self.normalize_url(href)
                        product_links.append(full_url)
                        self.logger.info(f"Добавлена ссылка товара {i+1}: {full_url}")
                    else:
                        self.logger.warning(f"Товар {i+1}: пустой href")
                else:
                    self.logger.warning(f"Товар {i+1}: не найдена ссылка")
                    
            except Exception as e:
                self.logger.error(f"Ошибка при извлечении ссылки товара {i+1}: {e}")
        
        self.logger.info(f"Извлечено {len(product_links)} ссылок на товары")
        return product_links
    
    def parse_product_page(self, product_url: str) -> Optional[Dict[str, Any]]:
        """
        Парсит отдельную страницу товара и извлекает всю информацию
        """
        self.logger.info(f"Парсинг страницы товара: {product_url}")
        
        html_content = self.get_html_content(product_url)
        if not html_content:
            self.logger.error(f"Не удалось получить HTML страницы {product_url}")
            return None
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        try:
            # Извлекаем основную информацию о товаре
            product_data = {
                'url': product_url,
                'name': '',
                'price': 0,
                'old_price': 0,
                'description': '',
                'characteristics': {},
                'images': [],
                'in_stock': True,
                'article': '',
                'meta_title': '',
                'meta_description': ''
            }
            
            # 1. Название товара
            title_selectors = [
                "h1.product-01__title",
                "h1",
                ".product-title",
                ".product-name"
            ]
            
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    product_data['name'] = clean_text(title_elem.get_text())
                    self.logger.info(f"Найдено название: {product_data['name']}")
                    break
            
            # 2. Цена товара
            price_selectors = [
                ".product-01__price",
                ".price-current",
                ".product-price",
                "[class*='price']"
            ]
            
            for selector in price_selectors:
                price_elem = soup.select_one(selector)
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    product_data['price'] = self.extract_price_from_text(price_text)
                    if product_data['price'] > 0:
                        self.logger.info(f"Найдена цена: {product_data['price']}")
                        break
            
            # 3. Старая цена (если есть скидка)
            old_price_selectors = [
                ".product-01__old-price",
                ".price-old",
                ".old-price"
            ]
            
            for selector in old_price_selectors:
                old_price_elem = soup.select_one(selector)
                if old_price_elem:
                    old_price_text = old_price_elem.get_text(strip=True)
                    product_data['old_price'] = self.extract_price_from_text(old_price_text)
                    if product_data['old_price'] > 0:
                        self.logger.info(f"Найдена старая цена: {product_data['old_price']}")
                        break
            
            # 4. Описание товара
            description_selectors = [
                ".product-01__description",
                ".product-description",
                ".product-info",
                "[class*='description']"
            ]
            
            for selector in description_selectors:
                desc_elem = soup.select_one(selector)
                if desc_elem:
                    product_data['description'] = clean_text(desc_elem.get_text())
                    self.logger.info(f"Найдено описание: {len(product_data['description'])} символов")
                    break
            
            # 5. Характеристики товара
            characteristics = {}
            
            # Способ 1: Таблица характеристик
            char_table = soup.select_one(".product-01__parameters, .characteristics-table, .product-specs")
            if char_table:
                rows = char_table.select("tr, .parameter-row, .spec-row")
                for row in rows:
                    cells = row.select("td, .param-name, .param-value")
                    if len(cells) >= 2:
                        key = clean_text(cells[0].get_text())
                        value = clean_text(cells[1].get_text())
                        if key and value:
                            characteristics[key] = value
            
            # Способ 2: Список характеристик
            if not characteristics:
                char_items = soup.select(".product-01__parameters-item, .characteristic-item")
                for item in char_items:
                    term_elem = item.select_one(".product-01__parameters-item-term, .char-name")
                    desc_elem = item.select_one(".product-01__parameters-item-desc, .char-value")
                    
                    if term_elem and desc_elem:
                        key = clean_text(term_elem.get_text())
                        value = clean_text(desc_elem.get_text())
                        if key and value:
                            characteristics[key] = value
            
            product_data['characteristics'] = characteristics
            self.logger.info(f"Найдено {len(characteristics)} характеристик")
            
            # 6. Изображения товара
            images = []
            
            # Основное изображение
            main_img_selectors = [
                ".product-01__gallery img",
                ".product-gallery img",
                ".product-image img",
                ".main-image img"
            ]
            
            for selector in main_img_selectors:
                img_elements = soup.select(selector)
                for i, img in enumerate(img_elements):
                    img_src = img.get('src') or img.get('data-src') or img.get('data-lazy')
                    if img_src:
                        full_img_url = self.normalize_url(img_src)
                        if full_img_url not in images:
                            images.append(full_img_url)
                
                if images:
                    break
            
            # Дополнительные изображения в галерее
            gallery_imgs = soup.select(".product-gallery__thumb img, .gallery-thumb img")
            for img in gallery_imgs:
                img_src = img.get('src') or img.get('data-src') or img.get('data-lazy')
                if img_src:
                    full_img_url = self.normalize_url(img_src)
                    if full_img_url not in images:
                        images.append(full_img_url)
            
            product_data['images'] = images
            self.logger.info(f"Найдено {len(images)} изображений")
            
            # 7. Артикул товара
            article_selectors = [
                ".product-01__article",
                ".product-article",
                ".sku"
            ]
            
            for selector in article_selectors:
                article_elem = soup.select_one(selector)
                if article_elem:
                    product_data['article'] = clean_text(article_elem.get_text())
                    break
            
            # 8. Наличие товара
            stock_indicators = [
                ".in-stock", ".available", ".product-01__stock"
            ]
            
            out_of_stock_indicators = [
                ".out-of-stock", ".not-available", ".sold-out"
            ]
            
            # Проверяем наличие
            for selector in out_of_stock_indicators:
                if soup.select_one(selector):
                    product_data['in_stock'] = False
                    break
            
            # 9. Мета-информация
            title_tag = soup.select_one("title")
            if title_tag:
                product_data['meta_title'] = clean_text(title_tag.get_text())
            
            meta_desc = soup.select_one("meta[name='description']")
            if meta_desc:
                product_data['meta_description'] = meta_desc.get('content', '')
            
            self.logger.info(f"Успешно спарсен товар: {product_data['name']}")
            return product_data
            
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге товара {product_url}: {e}", exc_info=True)
            return None
    
    async def parse_bunker_doors_products(self, catalog_url: str, db: AsyncSession) -> List[ProductCreate]:
        """
        Парсит товары с сайта Bunker Doors из указанного каталога
        Обновленная версия с парсингом отдельных страниц товаров
        """
        self.logger.info(f"Запуск парсера для каталога {catalog_url}")
        
        # Нормализация URL
        catalog_url = self.normalize_url(catalog_url)
        
        # Получаем каталог из URL
        catalog_slug = catalog_url.rstrip('/').split('/')[-1]
        
        # Формируем имя каталога
        catalog_name_part = catalog_slug.replace('-', ' ').title()
        catalog_name = f"Входные двери Bunker Doors {catalog_name_part}"
        
        # Получаем или обновляем каталог
        brand_id = await self.ensure_brand_exists(db)
        catalog = await self.get_or_create_catalog(db, catalog_name, catalog_slug, brand_id)
        
        if not catalog or catalog.id is None:
            self.logger.error(f"Не удалось создать каталог для {catalog_url}")
            return []
            
        catalog_id = catalog.id
        self.logger.info(f"Получен каталог с ID: {catalog_id}")
        
        # Получаем HTML страницы каталога
        html_content = self.get_html_content(catalog_url)
        if not html_content:
            return []
            
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Извлекаем ссылки на товары
        product_links = self.extract_product_links_from_page(soup, self.base_url)
        
        if not product_links:
            self.logger.warning(f"Не найдено ссылок на товары в каталоге {catalog_url}")
            return []
        
        self.logger.info(f"Найдено {len(product_links)} ссылок на товары")
        
        products = []
        
        # Ограничиваем количество товаров для тестирования (уберите это в продакшене)
        max_products = 5
        product_links = product_links[:max_products]
        
        # Парсим каждый товар отдельно
        for i, product_url in enumerate(product_links):
            try:
                self.logger.info(f"Обрабатываем товар {i+1}/{len(product_links)}: {product_url}")
                
                # Парсим страницу товара
                product_data = self.parse_product_page(product_url)
                
                if not product_data:
                    self.logger.warning(f"Не удалось спарсить товар {product_url}")
                    continue
                
                # Проверяем обязательные поля
                if not product_data['name']:
                    self.logger.warning(f"У товара {product_url} нет названия, пропускаем")
                    continue
                
                if product_data['price'] <= 0:
                    self.logger.warning(f"У товара {product_url} некорректная цена: {product_data['price']}")
                    # Устанавливаем цену по умолчанию или пропускаем
                    product_data['price'] = 1
                
                # Подготавливаем изображения
                images = []
                for j, img_url in enumerate(product_data['images']):
                    if self.is_valid_image_url(img_url):
                        images.append(ProductImageCreate(
                            url=img_url,
                            is_main=(j == 0)
                        ))
                
                # Если нет изображений, добавляем заглушку
                if not images:
                    images = [ProductImageCreate(
                        url="https://bunkerdoors.ru/images/no-photo.jpg",
                        is_main=True
                    )]
                
                # Генерируем slug
                product_slug = generate_slug(product_data['name'])
                
                # Создаем объект продукта
                product = ProductCreate(
                    name=product_data['name'],
                    price=product_data['price'],
                    discount_price=product_data['old_price'] if product_data['old_price'] > 0 else None,
                    description=product_data['description'] or f"Входная дверь {product_data['name']} от Bunker Doors",
                    catalog_id=catalog_id,
                    images=images,
                    image=images[0].url if images else None,
                    in_stock=product_data['in_stock'],
                    characteristics=product_data['characteristics'],
                    slug=product_slug,
                    meta_title=product_data['meta_title'] or f"{product_data['name']} - Bunker Doors",
                    meta_description=product_data['meta_description'] or product_data['description'][:500],
                    brand_id=brand_id,
                    attributes={
                        'article': product_data['article'],
                        'source_url': product_url
                    }
                )
                
                products.append(product)
                self.logger.info(f"Создан продукт: {product.name}, цена: {product.price}")
                
            except Exception as e:
                self.logger.error(f"Ошибка при обработке товара {product_url}: {e}", exc_info=True)
        
        self.logger.info(f"Успешно обработано {len(products)} товаров из каталога")
        return products
    
    def extract_price_from_text(self, text: str) -> int:
        """
        Извлекает цену из текста
        """
        if not text:
            return 0
        
        # Удаляем все кроме цифр и пробелов
        clean_text = re.sub(r'[^\d\s]', '', text)
        
        # Ищем числа
        numbers = re.findall(r'\d+', clean_text)
        
        if not numbers:
            return 0
        
        # Если несколько чисел, берем самое большое (обычно это цена)
        prices = [int(num) for num in numbers if len(num) >= 3]  # Цена обычно больше 100
        
        return max(prices) if prices else 0
    
    def is_valid_image_url(self, url: str) -> bool:
        """
        Проверяет, является ли URL корректным изображением
        """
        if not url:
            return False
        
        # Проверяем расширение
        valid_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
        url_lower = url.lower()
        
        return any(ext in url_lower for ext in valid_extensions)
    
    async def assign_product_to_all_categories(self, db: AsyncSession, product_id: int, 
                                             category_matches: List[Dict], default_category_id: int):
        """
        ИСПРАВЛЕННАЯ версия: Назначает продукт во все подходящие категории
        """
        try:
            # Очищаем старые связи с категориями
            await self.clear_product_categories(db, product_id)
            
            # Добавляем в основную категорию
            await self.add_product_to_category(db, product_id, default_category_id, is_primary=True)
            
            # Добавляем в дополнительные категории
            for category_match in category_matches:
                # ИСПРАВЛЕНИЕ: Извлекаем ID из словаря
                category_id = category_match['id']
                category_name = category_match['name']
                
                if category_id != default_category_id:
                    await self.add_product_to_category(db, product_id, category_id, is_primary=False)
                    self.logger.info(f"Продукт {product_id} добавлен в категорию '{category_name}' (ID: {category_id})")
            
        except Exception as e:
            self.logger.error(f"Ошибка при назначении категорий продукту {product_id}: {e}", exc_info=True)
            raise
    
    async def parse_multiple_catalogs(self, catalog_urls: List[str], db: AsyncSession) -> int:
        """
        Парсит несколько каталогов с улучшенной обработкой ошибок
        """
        self.logger.info(f"Запуск парсера для {len(catalog_urls)} каталогов")
        total_products = 0
        new_products = 0
        updated_products = 0
        
        # Получаем бренд один раз в начале процесса
        brand_id = await self.ensure_brand_exists(db)
        
        # Обновляем существующие каталоги, чтобы привязать их к бренду
        await self.update_catalogs_brand_id(db, brand_id)
        
        # Получаем ВСЕ общие категории из БД
        all_categories = await self.get_all_categories_from_db(db)
        
        if not all_categories:
            self.logger.error("В базе данных нет активных категорий!")
            return 0
        
        self.logger.info(f"Найдено {len(all_categories)} активных общих категорий в БД")
        
        # Получаем обязательную категорию "Все двери" 
        default_category = await self.get_default_category(db)
        
        if not default_category:
            self.logger.error("Не найдена категория 'Все двери' или аналогичная!")
            return 0
        
        default_category_id = default_category.id
        self.logger.info(f"Основная категория: '{default_category.name}' (ID: {default_category_id})")
        self.logger.info(f"Бренд для всех продуктов: '{self.brand_name}' (ID: {brand_id})")
        
        # Собираем продукты для последующей классификации
        products_to_classify = []
        
        for url in catalog_urls:
            try:
                products = await self.parse_bunker_doors_products(url, db)
                self.logger.info(f"Получено {len(products)} продуктов из каталога {url}")
                
                for product_in in products:
                    try:
                        # Проверка на существование продукта
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
                            # Собираем текст для анализа категорий
                            text_to_analyze = self._prepare_product_text_for_analysis(product_in)
                            
                            # Добавляем в список для классификации
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
                        self.logger.warning(f"Ошибка при обработке товара: {e}")
                        await db.rollback()
            
            except Exception as e:
                self.logger.error(f"Ошибка при обработке каталога {url}: {e}", exc_info=True)
                await db.rollback()

        # Делаем коммит всех созданных/обновленных продуктов
        try:
            await db.commit()
            self.logger.info(f"Успешно обработано {total_products} продуктов (новых: {new_products}, обновлено: {updated_products})")
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении продуктов: {e}", exc_info=True)
            await db.rollback()
            return 0

        # Классифицируем продукты по категориям
        if products_to_classify:
            try:
                self.logger.info(f"Начинаем классификацию {len(products_to_classify)} продуктов по категориям")
                
                classified_count = 0
                for product_id, text_to_analyze in products_to_classify:
                    # Классифицируем продукт по тексту
                    category_matches = await self.classify_product_to_categories(
                        text_to_analyze, 
                        all_categories,
                        min_matches=1
                    )
                    
                    # Назначаем продукт в подходящие категории
                    await self.assign_product_to_all_categories(
                        db, 
                        product_id, 
                        category_matches,
                        default_category_id,
                    )
                    
                    classified_count += 1
                
                # Коммитим все изменения по классификации
                await db.commit()
                self.logger.info(f"Успешно классифицировано {classified_count} продуктов")
                
                # Обновляем счетчики товаров в категориях
                await self.update_category_counters(db)
                
            except Exception as e:
                self.logger.error(f"Ошибка при классификации продуктов: {e}", exc_info=True)
                await db.rollback()

        self.logger.info(f"Итого: обработано {total_products} товаров (новых: {new_products}, обновлено: {updated_products})")
        return total_products

    def _prepare_product_text_for_analysis(self, product_in: ProductCreate) -> str:
        """
        Подготавливает текст продукта для анализа категорий
        """
        text_parts = []
        
        # Название продукта (самый важный текст)
        if product_in.name:
            text_parts.append(product_in.name)
        
        # Описание
        if product_in.description:
            text_parts.append(product_in.description)
        
        # Характеристики
        if product_in.characteristics:
            for key, value in product_in.characteristics.items():
                text_parts.append(f"{key} {value}")
        
        # Мета-информация
        if hasattr(product_in, 'meta_title') and product_in.meta_title:
            text_parts.append(product_in.meta_title)
        
        if hasattr(product_in, 'meta_description') and product_in.meta_description:
            text_parts.append(product_in.meta_description)
        
        return " ".join(text_parts)