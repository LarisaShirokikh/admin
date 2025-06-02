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
from app.models.catalog import Catalog
from app.schemas.product import ProductCreate
from app.schemas.product_image import ProductImageCreate
from app.utils.text_utils import generate_slug, clean_text
from app.crud.product import create_or_update_product
from app.scrapers.base_scraper import BaseScraper

logger = logging.getLogger("bunker_doors_scraper")

class BunkerDoorsScraper(BaseScraper):
    def __init__(self):
        super().__init__(
            brand_name="Бункер",
            brand_slug="bunker",
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
    
    def get_pagination_urls(self, soup: BeautifulSoup, current_url: str) -> List[str]:
        """
        НОВОЕ: Извлекает URL страниц пагинации
        """
        pagination_urls = []
        
        # Ищем элементы пагинации
        pagination_selectors = [
            ".pagination a",
            ".pages a", 
            ".page-numbers a",
            "a[href*='page']"
        ]
        
        for selector in pagination_selectors:
            links = soup.select(selector)
            if links:
                for link in links:
                    href = link.get('href')
                    if href and href != current_url:
                        full_url = self.normalize_url(href)
                        if full_url not in pagination_urls:
                            pagination_urls.append(full_url)
                break
        
        self.logger.info(f"Найдено {len(pagination_urls)} страниц пагинации")
        return pagination_urls
    
    def parse_product_page(self, product_url: str) -> Optional[Dict[str, Any]]:
        """
        ИСПРАВЛЕНО: Парсит отдельную страницу товара с правильными селекторами
        """
        self.logger.debug(f"Парсинг страницы товара: {product_url}")
        
        html_content = self.get_html_content(product_url)
        if not html_content:
            self.logger.error(f"Не удалось получить HTML страницы {product_url}")
            return None
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        try:
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
            
            # 1. Название товара (ИСПРАВЛЕНО)
            title_selectors = [
                "h1.product-01__title",
                ".product-title h1",
                "h1"
            ]
            
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    product_data['name'] = clean_text(title_elem.get_text())
                    self.logger.debug(f"Найдено название: {product_data['name']}")
                    break
            
            # 2. Цена товара (ИСПРАВЛЕНО)
            price_elem = soup.select_one(".product-01__price")
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                product_data['price'] = self.extract_price_from_text(price_text)
                if product_data['price'] > 0:
                    self.logger.debug(f"Найдена цена: {product_data['price']}")
            
            # 3. Старая цена (если есть скидка)
            old_price_elem = soup.select_one(".product-01__old-price")
            if old_price_elem:
                old_price_text = old_price_elem.get_text(strip=True)
                product_data['old_price'] = self.extract_price_from_text(old_price_text)
                if product_data['old_price'] > 0:
                    self.logger.debug(f"Найдена старая цена: {product_data['old_price']}")
            
            # 4. ИСПРАВЛЕНО: Описание из секции product-description
            description_parts = []
            
            # Основное описание
            desc_elem = soup.select_one(".product-description")
            if desc_elem:
                description_parts.append(clean_text(desc_elem.get_text()))
            
            # Дополнительное описание из других секций
            additional_desc = soup.select_one(".product-01__description")
            if additional_desc:
                description_parts.append(clean_text(additional_desc.get_text()))
            
            product_data['description'] = " ".join(description_parts).strip()
            
            # 5. ИСПРАВЛЕНО: Характеристики из списка параметров
            characteristics = {}
            
            # Парсим характеристики из списка
            param_items = soup.select(".product-01__parameters-item")
            for item in param_items:
                term_elem = item.select_one(".product-01__parameters-item-term")
                desc_elem = item.select_one(".product-01__parameters-item-desc")
                
                if term_elem and desc_elem:
                    key = clean_text(term_elem.get_text())
                    value = clean_text(desc_elem.get_text())
                    if key and value:
                        characteristics[key] = value
            
            product_data['characteristics'] = characteristics
            self.logger.debug(f"Найдено {len(characteristics)} характеристик")
            
            # 6. ИСПРАВЛЕНО: Изображения
            images = []
            
            # Главное изображение
            main_image = soup.select_one(".product-gallery-04__stage-item-img-container")
            if main_image:
                img_url = main_image.get('href')
                if img_url:
                    full_img_url = self.normalize_url(img_url)
                    if self.is_valid_image_url(full_img_url):
                        images.append(full_img_url)
            
            # Дополнительные изображения из галереи
            gallery_images = soup.select(".product-gallery-04__list-item img")
            for img in gallery_images:
                img_src = img.get('data-bc-lazy-path') or img.get('src')
                if img_src:
                    full_img_url = self.normalize_url(img_src)
                    if self.is_valid_image_url(full_img_url) and full_img_url not in images:
                        images.append(full_img_url)
            
            # Если не нашли изображения, ищем альтернативными способами
            if not images:
                alt_images = soup.select(".product-01 img, .product-gallery img")
                for img in alt_images:
                    img_src = img.get('src') or img.get('data-src')
                    if img_src:
                        full_img_url = self.normalize_url(img_src)
                        if self.is_valid_image_url(full_img_url) and full_img_url not in images:
                            images.append(full_img_url)
            
            product_data['images'] = images
            self.logger.debug(f"Найдено {len(images)} изображений")
            
            # 7. Артикул товара
            article_elem = soup.select_one(".product-01__article")
            if article_elem:
                article_text = clean_text(article_elem.get_text())
                # Извлекаем только артикул из текста
                article_match = re.search(r'([A-Za-z0-9\-]+)', article_text)
                if article_match:
                    product_data['article'] = article_match.group(1)
            
            # 8. Наличие товара
            in_stock = True
            # Проверяем наличие индикаторов "нет в наличии"
            page_text = soup.get_text().lower()
            if any(phrase in page_text for phrase in ['нет в наличии', 'под заказ', 'недоступен']):
                in_stock = False
            
            product_data['in_stock'] = in_stock
            
            # 9. Мета-информация
            title_tag = soup.select_one("title")
            if title_tag:
                product_data['meta_title'] = clean_text(title_tag.get_text())
            
            meta_desc = soup.select_one("meta[name='description']")
            if meta_desc:
                product_data['meta_description'] = meta_desc.get('content', '')
            
            self.logger.debug(f"Успешно спарсен товар: {product_data['name']}")
            return product_data
            
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге товара {product_url}: {e}", exc_info=True)
            return None
    
    async def parse_bunker_doors_products(self, catalog_url: str, db: AsyncSession) -> List[ProductCreate]:
        """
        Парсит товары с сайта Bunker Doors из указанного каталога
        """
        self.logger.info(f"Запуск парсера для каталога {catalog_url}")
        
        # Нормализация URL
        catalog_url = self.normalize_url(catalog_url)
        
        # Получаем каталог из URL
        catalog_slug = catalog_url.rstrip('/').split('/')[-1]
        
        # Формируем имя каталога
        catalog_name_part = catalog_slug.replace('-', ' ').title()
        catalog_name = f"Входные двери Бункер {catalog_name_part}"
        
        # Получаем или создаем каталог
        brand_id = await self.ensure_brand_exists(db)
        await db.commit()
        catalog = await self.get_or_create_catalog(db, catalog_name, catalog_slug, brand_id)
        await db.commit()
        
        # Проверяем, что каталог создан и имеет ID
        if not catalog or catalog.id is None:
            self.logger.error(f"Не удалось создать каталог для {catalog_url}")
            return []
            
        catalog_id = catalog.id
        self.logger.info(f"Получен каталог с ID: {catalog_id}")

        from app.models.catalog import Catalog
        result = await db.execute(select(Catalog).where(Catalog.id == catalog_id))
        catalog_check = result.scalar_one_or_none()
        
        if not catalog_check:
            self.logger.error(f"КРИТИЧЕСКАЯ ОШИБКА: Каталог с ID {catalog_id} не найден в базе данных после создания!")
            return []
        
        self.logger.info(f"Проверка каталога пройдена: '{catalog_check.name}' существует в БД")
    
        
        # Собираем все ссылки на товары (включая пагинацию)
        all_product_links = []
        processed_urls = set()
        urls_to_process = [catalog_url]
        
        while urls_to_process:
            current_url = urls_to_process.pop(0)
            
            if current_url in processed_urls:
                continue
                
            processed_urls.add(current_url)
            
            self.logger.info(f"Обработка страницы: {current_url}")
            
            # Получаем HTML страницы каталога
            html_content = self.get_html_content(current_url)
            if not html_content:
                self.logger.warning(f"Не удалось получить контент страницы {current_url}")
                continue
                
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Извлекаем ссылки на товары
            product_links = self.extract_product_links_from_page(soup, self.base_url)
            all_product_links.extend(product_links)
            
            # Получаем ссылки на следующие страницы
            pagination_urls = self.get_pagination_urls(soup, current_url)
            for page_url in pagination_urls:
                if page_url not in processed_urls:
                    urls_to_process.append(page_url)
        
        if not all_product_links:
            self.logger.warning(f"Не найдено ссылок на товары в каталоге {catalog_url}")
            return []
        
        self.logger.info(f"Найдено {len(all_product_links)} ссылок на товары")
        
        products = []
        first_product_image = None  # Для сохранения первого изображения продукта
        
        # Парсим каждый товар отдельно
        for i, product_url in enumerate(all_product_links):
            try:
                self.logger.info(f"Обрабатываем товар {i+1}/{len(all_product_links)}: {product_url}")
                
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
                    self.logger.warning(f"У товара {product_url} некорректная цена: {product_data['price']}, устанавливаем 1")
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
                
                # Если это первый продукт с изображениями, сохраняем его изображение для каталога
                if not first_product_image and images:
                    first_product_image = images[0].url
                    await self.update_catalog_image(db, catalog, first_product_image)
                
                # Генерируем slug
                product_slug = generate_slug(product_data['name'])

                description = product_data['description'] or f"Входная дверь {product_data['name']} от Бункер"

                # Добавляем характеристики в описание
                if product_data['characteristics']:
                    characteristics_text = []
                    for key, value in product_data['characteristics'].items():
                        if key and value:
                            characteristics_text.append(f"• {key}: {value}")
                    
                    if characteristics_text:
                        description += "\n\n📋 Технические характеристики:\n" + "\n".join(characteristics_text)

                
                # Создаем мета-описание
                meta_description = self.create_meta_description(product_data['description'], product_data['characteristics'])
                
                # Создаем объект продукта
                product = ProductCreate(
                    name=product_data['name'],
                    price=product_data['price'],
                    discount_price=product_data['old_price'] if product_data['old_price'] > 0 else None,
                    description=description,  # Полное описание с характеристиками
                    catalog_id=catalog_id,
                    images=images,
                    image=images[0].url if images else None,
                    in_stock=product_data['in_stock'],
                    slug=product_slug,
                    meta_title=product_data['meta_title'] or f"{product_data['name']} - Бункер",
                    meta_description=meta_description[:500],
                    brand_id=brand_id,
                    article=product_data['article']
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
        Парсит несколько каталогов (точно как в Лабиринте)
        """
        self.logger.info(f"Запуск парсера для {len(catalog_urls)} каталогов")
        total_products = 0
        new_products = 0
        updated_products = 0
        
        # Получаем бренд
        brand_id = await self.ensure_brand_exists(db)
        
        # Обновляем существующие каталоги
        await self.update_catalogs_brand_id(db, brand_id)
        
        # ШАГИ ПОДГОТОВКИ КАТЕГОРИЙ
        
        # 1. Получаем ВСЕ категории из БД
        all_categories = await self.get_all_categories_from_db(db)
        
        if not all_categories:
            self.logger.error("В базе данных нет активных категорий!")
            return 0
        
        self.logger.info(f"Найдено {len(all_categories)} активных категорий в БД")
        
        # 2. Получаем обязательную категорию "Все двери"
        default_category = await self.get_default_category(db)
        
        if not default_category:
            self.logger.error("Не найдена категория 'Все двери' или аналогичная!")
            return 0
        
        default_category_id = default_category.id
        self.logger.info(f"Основная категория: '{default_category.name}' (ID: {default_category_id})")
        self.logger.info(f"Бренд для всех продуктов: '{self.brand_name}' (ID: {brand_id})")
        
        # ПАРСИНГ И СОЗДАНИЕ ПРОДУКТОВ
        products_to_classify = []
        
        for url in catalog_urls:
            try:
                products = await self.parse_bunker_doors_products(url, db)
                self.logger.info(f"Получено {len(products)} продуктов из каталога {url}")
                
                for product_in in products:
                    try:
                        # Проверка на существование
                        result = await db.execute(
                            select(Product).where(
                                or_(
                                    Product.slug == product_in.slug,
                                    func.lower(Product.name) == product_in.name.lower()
                                )
                            )
                        )
                        existing_product = result.scalar_one_or_none()
                        
                        # Создаем/обновляем продукт
                        created_product = await create_or_update_product(db, product_in)
                        
                        if created_product:
                            # Собираем ВЕСЬ текст для анализа категорий
                            analysis_text = self._prepare_product_text_for_analysis(product_in)
                            
                            # Добавляем в очередь для классификации
                            products_to_classify.append({
                                'product_id': created_product.id,
                                'text': analysis_text,
                                'name': product_in.name
                            })
                            
                            # Счетчики
                            total_products += 1
                            if existing_product:
                                updated_products += 1
                            else:
                                new_products += 1
                                
                            await db.flush()
                        
                    except Exception as e:
                        self.logger.warning(f"Ошибка при обработке товара: {e}")
                        await db.rollback()
            
            except Exception as e:
                self.logger.error(f"Ошибка при обработке каталога {url}: {e}", exc_info=True)
                await db.rollback()
        
        # Коммитим созданные продукты
        try:
            await db.commit()
            self.logger.info(f"Сохранено {total_products} продуктов (новых: {new_products}, обновлено: {updated_products})")
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении продуктов: {e}", exc_info=True)
            await db.rollback()
            return 0
        
        # КЛАССИФИКАЦИЯ ПО КАТЕГОРИЯМ
        if products_to_classify:
            self.logger.info(f"Начинаем классификацию {len(products_to_classify)} продуктов")
            
            classified_count = 0
            
            for product_info in products_to_classify:
                try:
                    product_id = product_info['product_id']
                    product_text = product_info['text']
                    product_name = product_info['name']
                    
                    # Находим подходящие дополнительные категории
                    additional_categories = await self.classify_product_to_categories(
                        product_text, 
                        all_categories,
                        min_matches=1  # Минимум 1 совпадение
                    )
                    
                    # Назначаем продукт в категории (обязательно в "Все двери" + дополнительные)
                    await self.assign_product_to_all_categories(
                        db,
                        product_id,
                        default_category_id,
                        additional_categories
                    )
                    
                    classified_count += 1
                    
                    # Логируем результат классификации
                    additional_names = [cat['name'] for cat in additional_categories[:3]]  # Первые 3
                    self.logger.debug(f"Продукт '{product_name}' -> Все двери + {additional_names}")
                    
                except Exception as e:
                    self.logger.error(f"Ошибка при классификации продукта {product_info.get('name', 'Unknown')}: {e}")
                    continue
            
            # Коммитим все изменения по категориям
            try:
                await db.commit()
                self.logger.info(f"Успешно классифицировано {classified_count} продуктов")
                
                # Обновляем счетчики товаров в категориях
                await self.update_category_counters(db)
                
            except Exception as e:
                self.logger.error(f"Ошибка при сохранении классификации: {e}", exc_info=True)
                await db.rollback()
        
        self.logger.info(f"ИТОГО: {total_products} товаров (новых: {new_products}, обновлено: {updated_products})")
        return total_products

    def _prepare_product_text_for_analysis(self, product_in: ProductCreate) -> str:
        """
        УПРОЩЕНО: Подготовка текста продукта для анализа категорий
        (характеристики теперь в описании)
        """
        text_parts = []
        
        # Название продукта (самый важный текст)
        if hasattr(product_in, 'name') and product_in.name:
            text_parts.append(product_in.name)
        
        # Описание (теперь уже содержит характеристики)
        if hasattr(product_in, 'description') and product_in.description:
            text_parts.append(product_in.description)
        
        # Мета-информация
        if hasattr(product_in, 'meta_title') and product_in.meta_title:
            text_parts.append(product_in.meta_title)
        
        if hasattr(product_in, 'meta_description') and product_in.meta_description:
            text_parts.append(product_in.meta_description)
        
        # Артикул (если есть)
        if hasattr(product_in, 'article') and product_in.article:
            text_parts.append(product_in.article)
        
        result = " ".join(text_parts)
        self.logger.debug(f"Подготовлен текст для анализа ({len(result)} символов): {result[:100]}...")
        return result