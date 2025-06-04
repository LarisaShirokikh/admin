"""
Исправленный скрапер для сайта Bunker Doors с правильной структурой класса
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
        Извлекает URL страниц пагинации
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
        ИСПРАВЛЕННАЯ ВЕРСИЯ: Парсит отдельную страницу товара с правильным извлечением характеристик и описания
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
            
            # 1. Название товара
            title_selectors = [
                "h1.product-01__title",
                ".product-title h1",
                "h1"
            ]
            
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    product_data['name'] = clean_text(title_elem.get_text())
                    self.logger.info(f"🏷️ Найдено название: {product_data['name']}")
                    break
            
            # 2. Цена товара
            price_elem = soup.select_one(".product-01__price")
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                product_data['price'] = self.extract_price_from_text(price_text)
                self.logger.info(f"💰 Найдена цена: {product_data['price']} (текст: {price_text})")
            
            # 3. Старая цена
            old_price_elem = soup.select_one(".product-01__old-price")
            if old_price_elem:
                old_price_text = old_price_elem.get_text(strip=True)
                product_data['old_price'] = self.extract_price_from_text(old_price_text)
                self.logger.info(f"💸 Найдена старая цена: {product_data['old_price']}")
            
            # 4. ИСПРАВЛЕННЫЙ ПАРСИНГ ОПИСАНИЯ
            description_parts = []

            # Расширенный список селекторов для описания
            desc_selectors = [
                ".product-description",
                ".product-01__description", 
                ".product-content",
                ".product-info",
                ".description",
                ".product-details",
                ".product-text"
            ]

            self.logger.info(f"📝 Ищем описание товара...")

            for selector in desc_selectors:
                desc_elements = soup.select(selector)
                self.logger.info(f"📝 Селектор '{selector}': найдено {len(desc_elements)} элементов")
                
                for i, desc_elem in enumerate(desc_elements):
                    if desc_elem:
                        desc_text = clean_text(desc_elem.get_text())
                        if desc_text and len(desc_text.strip()) > 10:  # Минимум 10 символов
                            description_parts.append(desc_text)
                            self.logger.info(f"📝 ✅ Найдено описание #{i+1} ({len(desc_text)} символов): {desc_text[:100]}...")
                        else:
                            self.logger.info(f"📝 ❌ Описание #{i+1} слишком короткое или пустое: '{desc_text}'")

            # Если не нашли описание, ищем в общих блоках
            if not description_parts:
                self.logger.warning(f"📝 Основные селекторы не дали результата, ищем альтернативные описания")
                
                # Альтернативные селекторы
                alt_desc_selectors = [
                    ".product .content",
                    ".product .text", 
                    "article",
                    ".main-content p",
                    ".product-wrapper .text"
                ]
                
                for alt_selector in alt_desc_selectors:
                    alt_elements = soup.select(alt_selector)
                    self.logger.info(f"📝 Альтернативный селектор '{alt_selector}': найдено {len(alt_elements)} элементов")
                    
                    for elem in alt_elements:
                        alt_text = clean_text(elem.get_text())
                        if alt_text and len(alt_text.strip()) > 20:
                            description_parts.append(alt_text)
                            self.logger.info(f"📝 ✅ Альтернативное описание найдено: {alt_text[:100]}...")
                            break
                    
                    if description_parts:
                        break

            # Объединяем все части описания
            final_description = " ".join(description_parts).strip()
            product_data['description'] = final_description

            self.logger.info(f"📝 ИТОГО описание ({len(final_description)} символов): {final_description[:200]}...")

            if not final_description:
                self.logger.warning(f"📝 ❌ ОПИСАНИЕ НЕ НАЙДЕНО!")
                
                # Показываем структуру страницы для диагностики
                main_blocks = soup.select(".product, .main, .content, article")
                self.logger.info(f"📝 Основные блоки на странице: {len(main_blocks)}")
                for i, block in enumerate(main_blocks[:3]):
                    block_text = clean_text(block.get_text())
                    if block_text:
                        self.logger.info(f"📝 Блок {i+1} ({len(block_text)} символов): {block_text[:150]}...")
            else:
                self.logger.info(f"📝 ✅ Описание успешно извлечено")
            
            # 5. ИСПРАВЛЕННЫЙ ПАРСИНГ ХАРАКТЕРИСТИК
            characteristics = {}
            param_items = soup.select(".product-01__parameters-item")
            self.logger.info(f"⚙️ Найдено {len(param_items)} элементов характеристик")

            for i, item in enumerate(param_items):
                self.logger.info(f"⚙️ Элемент характеристики {i+1}: {str(item)[:200]}...")
                
                # Пробуем разные селекторы для термина и описания
                term_selectors = [
                    ".product-01__parameters-item-term",
                    ".parameters-item-term", 
                    ".term",
                    "dt"
                ]
                
                desc_selectors = [
                    ".product-01__parameters-item-desc",
                    ".parameters-item-desc",
                    ".desc", 
                    "dd"
                ]
                
                term_elem = None
                desc_elem = None
                
                # Ищем термин
                for term_selector in term_selectors:
                    term_elem = item.select_one(term_selector)
                    if term_elem:
                        self.logger.info(f"⚙️ Термин найден через селектор '{term_selector}'")
                        break
                
                # Ищем описание
                for desc_selector in desc_selectors:
                    desc_elem = item.select_one(desc_selector)
                    if desc_elem:
                        self.logger.info(f"⚙️ Описание найдено через селектор '{desc_selector}'")
                        break
                
                # Если не нашли через селекторы, пробуем извлечь из всего элемента
                if not term_elem or not desc_elem:
                    self.logger.info(f"⚙️ Селекторы не сработали, пробуем альтернативный парсинг")
                    
                    # Получаем весь текст элемента
                    full_text = clean_text(item.get_text())
                    self.logger.info(f"⚙️ Полный текст элемента: '{full_text}'")
                    
                    # Пробуем разделить по двоеточию или другим разделителям
                    if ':' in full_text:
                        parts = full_text.split(':', 1)
                        if len(parts) == 2:
                            key = clean_text(parts[0])
                            value = clean_text(parts[1])
                            if key and value:
                                characteristics[key] = value
                                self.logger.info(f"⚙️ Извлечено через двоеточие: '{key}' = '{value}'")
                            continue
                    
                    # Пробуем найти все текстовые узлы
                    text_nodes = []
                    for child in item.descendants:
                        if hasattr(child, 'string') and child.string and child.string.strip():
                            text_content = clean_text(child.string)
                            if text_content and len(text_content) > 1:
                                text_nodes.append(text_content)
                    
                    self.logger.info(f"⚙️ Найдено текстовых узлов: {text_nodes}")
                    
                    if len(text_nodes) >= 2:
                        key = text_nodes[0]
                        value = ' '.join(text_nodes[1:])
                        if key and value:
                            characteristics[key] = value
                            self.logger.info(f"⚙️ Извлечено из узлов: '{key}' = '{value}'")
                    continue
                
                # Обычный парсинг через найденные элементы
                if term_elem and desc_elem:
                    key = clean_text(term_elem.get_text())
                    value = clean_text(desc_elem.get_text())
                    
                    self.logger.info(f"⚙️ Сырые данные: термин='{term_elem.get_text()}', описание='{desc_elem.get_text()}'")
                    self.logger.info(f"⚙️ Очищенные данные: ключ='{key}', значение='{value}'")
                    
                    if key and value:
                        characteristics[key] = value
                        self.logger.info(f"⚙️ ✅ Добавлена характеристика: '{key}' = '{value}'")
                    else:
                        self.logger.warning(f"⚙️ ❌ Пустые данные после очистки")

            product_data['characteristics'] = characteristics
            self.logger.info(f"⚙️ ИТОГО извлечено характеристик: {len(characteristics)}")

            # Выводим все найденные характеристики
            if characteristics:
                self.logger.info(f"⚙️ Список всех характеристик:")
                for key, value in characteristics.items():
                    self.logger.info(f"⚙️   • {key}: {value}")
            else:
                self.logger.warning(f"⚙️ Характеристики НЕ найдены!")
                
                # Дополнительная отладка - ищем ВСЕ возможные элементы с характеристиками
                self.logger.info(f"⚙️ Дополнительный поиск характеристик...")
                
                # Ищем альтернативные селекторы
                alt_selectors = [
                    ".parameters li",
                    ".product-parameters .item", 
                    ".characteristics .row",
                    ".specs dt, .specs dd",
                    "dl dt, dl dd"
                ]
                
                for alt_selector in alt_selectors:
                    alt_elements = soup.select(alt_selector)
                    if alt_elements:
                        self.logger.info(f"⚙️ Альтернативный селектор '{alt_selector}': найдено {len(alt_elements)} элементов")
                        for j, elem in enumerate(alt_elements[:3]):  # Показываем первые 3
                            self.logger.info(f"⚙️ Элемент {j+1}: {clean_text(elem.get_text())}")
                        break
            
            # 6. ИСПРАВЛЕННЫЕ ИЗОБРАЖЕНИЯ - новые селекторы по реальной структуре HTML
            images = []
            
            self.logger.info(f"🖼️ === НАЧИНАЕМ ПОИСК ИЗОБРАЖЕНИЙ для {product_url} ===")
            
            # Проверяем наличие галереи в HTML
            gallery_check = soup.select(".product-gallery-04")
            self.logger.info(f"🖼️ Контейнеров .product-gallery-04: {len(gallery_check)}")
            
            if gallery_check:
                gallery_html = str(gallery_check[0])[:500]
                self.logger.info(f"🖼️ HTML галереи (первые 500 символов): {gallery_html}")
            
            # Метод 1: Главное изображение из контейнера
            main_containers = soup.select(".product-gallery-04__stage-item-img-container")
            self.logger.info(f"🖼️ Главных контейнеров: {len(main_containers)}")
            
            for i, container in enumerate(main_containers):
                href = container.get('href')
                self.logger.info(f"🖼️ Контейнер {i+1}: href='{href}'")
                
                if href:
                    # Проверяем сырой href
                    self.logger.info(f"🖼️ Сырой href: '{href}'")
                    
                    # Нормализуем URL
                    if href.startswith('/'):
                        full_url = f"https://bunkerdoors.ru{href}"
                    elif href.startswith('http'):
                        full_url = href
                    else:
                        full_url = f"https://bunkerdoors.ru/{href}"
                    
                    self.logger.info(f"🖼️ Нормализованный URL: '{full_url}'")
                    
                    # Проверяем валидность
                    if self._debug_is_valid_image_url(full_url):
                        images.append(full_url)
                        self.logger.info(f"✅ Добавлено главное изображение: {full_url}")
                    else:
                        self.logger.warning(f"❌ Главное изображение не прошло валидацию: {full_url}")
            
            # Метод 2: Изображения из галереи (ИСПРАВЛЕННЫЙ)
            gallery_img_selectors = [
                ".product-gallery-04__item img",
                ".product-gallery-04__stage-item img", 
                ".product-gallery img",
                ".gallery img"
            ]
            
            for selector in gallery_img_selectors:
                gallery_images = soup.select(selector)
                self.logger.info(f"🖼️ Селектор '{selector}': найдено {len(gallery_images)} изображений")
                
                for i, img in enumerate(gallery_images):
                    self.logger.info(f"🖼️ IMG {i+1} атрибуты: {dict(img.attrs)}")
                    
                    # ИСПРАВЛЕНО: Правильная обработка lazy loading атрибутов
                    img_url = None
                    
                    # Способ 1: Объединяем data-bc-lazy-path + data-bc-lazy-filename
                    lazy_path = img.get('data-bc-lazy-path')
                    lazy_filename = img.get('data-bc-lazy-filename')
                    
                    if lazy_path and lazy_filename:
                        # Убираем лишние слеши и объединяем
                        lazy_path = lazy_path.rstrip('/')
                        img_url = f"{lazy_path}/{lazy_filename}"
                        self.logger.info(f"🖼️ Собрано из lazy: {lazy_path} + {lazy_filename} = {img_url}")
                    
                    # Способ 2: Прямые атрибуты (если lazy не сработал)
                    if not img_url:
                        for attr in ['src', 'data-src', 'data-original']:
                            attr_value = img.get(attr)
                            if attr_value and not attr_value.startswith('data:'):  # Исключаем SVG заглушки
                                img_url = attr_value
                                self.logger.info(f"🖼️ Найден атрибут {attr}: '{img_url}'")
                                break
                    
                    # Обрабатываем найденный URL
                    if img_url:
                        # Нормализуем URL
                        if img_url.startswith('/'):
                            full_url = f"https://bunkerdoors.ru{img_url}"
                        elif img_url.startswith('http'):
                            full_url = img_url
                        else:
                            full_url = f"https://bunkerdoors.ru/{img_url}"
                        
                        self.logger.info(f"🖼️ Нормализованный URL: '{full_url}'")
                        
                        # ИСПРАВЛЕННАЯ валидация (исключаем папки)
                        if self._debug_is_valid_image_url(full_url) and full_url not in images:
                            images.append(full_url)
                            self.logger.info(f"✅ Добавлено изображение: {full_url}")
                        else:
                            self.logger.warning(f"❌ Изображение не прошло валидацию: {full_url}")
                
                # Если нашли изображения, прекращаем поиск
                if images:
                    self.logger.info(f"🖼️ Нашли изображения через селектор '{selector}', прекращаем поиск")
                    break
            
            # Метод 3: Поиск всех изображений на странице (если ничего не нашли)
            if not images:
                self.logger.warning("🖼️ Основные методы не дали результата, ищем ВСЕ изображения")
                
                all_images = soup.find_all('img')
                self.logger.info(f"🖼️ Всего IMG тегов на странице: {len(all_images)}")
                
                for i, img in enumerate(all_images):
                    img_attrs = dict(img.attrs)
                    self.logger.info(f"🖼️ Глобальное IMG {i+1}: {img_attrs}")
                    
                    # Ищем любые атрибуты с изображениями
                    for attr_name, attr_value in img_attrs.items():
                        if isinstance(attr_value, str) and ('/images/' in attr_value or 'product' in attr_value.lower()):
                            if attr_value.startswith('/'):
                                full_url = f"https://bunkerdoors.ru{attr_value}"
                            else:
                                full_url = attr_value
                            
                            if self._debug_is_valid_image_url(full_url) and full_url not in images:
                                images.append(full_url)
                                self.logger.info(f"✅ Найдено глобальным поиском: {full_url}")
            
            product_data['images'] = images
            self.logger.info(f"🎯 ИТОГО НАЙДЕНО ИЗОБРАЖЕНИЙ: {len(images)}")
            
            if images:
                for i, img in enumerate(images):
                    self.logger.info(f"   {i+1}. {img}")
            else:
                self.logger.error(f"❌ НИ ОДНОГО ИЗОБРАЖЕНИЯ НЕ НАЙДЕНО для {product_url}")
            
            # 7. Артикул товара
            article_elem = soup.select_one(".product-01__article")
            if article_elem:
                article_text = clean_text(article_elem.get_text())
                article_match = re.search(r'([A-Za-z0-9\-]+)', article_text)
                if article_match:
                    product_data['article'] = article_match.group(1)
                    self.logger.info(f"🏷️ Найден артикул: {product_data['article']}")
            
            # 8. Наличие товара
            in_stock = True
            page_text = soup.get_text().lower()
            if any(phrase in page_text for phrase in ['нет в наличии', 'под заказ', 'недоступен']):
                in_stock = False
            
            product_data['in_stock'] = in_stock
            self.logger.info(f"📦 В наличии: {in_stock}")
            
            # 9. Мета-информация
            title_tag = soup.select_one("title")
            if title_tag:
                product_data['meta_title'] = clean_text(title_tag.get_text())
            
            meta_desc = soup.select_one("meta[name='description']")
            if meta_desc:
                product_data['meta_description'] = meta_desc.get('content', '')
            
            self.logger.info(f"✅ Парсинг завершен для: {product_data['name']}")
            return product_data
            
        except Exception as e:
            self.logger.error(f"💥 Ошибка при парсинге товара {product_url}: {e}", exc_info=True)
            return None

    def _debug_is_valid_image_url(self, url: str) -> bool:
        """
        ИСПРАВЛЕННАЯ валидация URL изображения с исключением папок
        """
        if not url:
            self.logger.debug(f"🔍 URL пустой")
            return False
        
        url_lower = url.lower()
        
        # ИСПРАВЛЕНИЕ 1: Исключаем папки (URL заканчивающиеся на /)
        if url.endswith('/'):
            self.logger.info(f"🔍 URL заканчивается на '/' - это папка, не файл: {url}")
            return False
        
        # ИСПРАВЛЕНИЕ 2: Исключаем SVG заглушки
        if 'data:image/svg+xml' in url:
            self.logger.info(f"🔍 URL содержит SVG заглушку: {url}")
            return False
        
        # Проверяем расширение
        valid_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
        has_extension = any(url_lower.endswith(ext) for ext in valid_extensions)
        
        # Проверяем паттерны
        has_images_path = '/images/' in url_lower
        has_product = 'product' in url_lower
        
        # Исключения
        excluded_patterns = ['no-photo', 'placeholder', 'icon', 'logo', 'thumb', 'sprite']
        is_excluded = any(pattern in url_lower for pattern in excluded_patterns)
        
        # Минимальная длина
        is_long_enough = len(url) > 20  # Увеличили минимальную длину
        
        # ИСПРАВЛЕНИЕ 3: Более строгая валидация - требуем либо расширение, либо /images/ в пути
        result = (has_extension or has_images_path) and not is_excluded and is_long_enough
        
        self.logger.info(f"🔍 Валидация '{url}': ext={has_extension}, images={has_images_path}, product={has_product}, excluded={is_excluded}, long={is_long_enough} -> {result}")
        
        return result
    
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
                
                # 📸 ИСПРАВЛЕННАЯ ПОДГОТОВКА ИЗОБРАЖЕНИЙ
                images = []
                valid_image_urls = []

                # Сначала фильтруем и логируем все найденные URL
                self.logger.info(f"📸 Обработка изображений для товара '{product_data['name']}'")
                self.logger.info(f"📸 Сырые URL из парсера: {product_data['images']}")

                for j, img_url in enumerate(product_data['images']):
                    if img_url and isinstance(img_url, str):
                        # Дополнительная очистка URL
                        cleaned_url = img_url.strip()
                        
                        # Проверяем валидность еще раз
                        if self.is_valid_image_url(cleaned_url):
                            valid_image_urls.append(cleaned_url)
                            self.logger.info(f"📸 Валидное изображение {j+1}: {cleaned_url}")
                        else:
                            self.logger.warning(f"📸 Невалидное изображение {j+1}: {cleaned_url}")
                    else:
                        self.logger.warning(f"📸 Пустой или некорректный URL {j+1}: {img_url}")

                # Создаем объекты ProductImageCreate только из валидных URL
                for j, img_url in enumerate(valid_image_urls):
                    try:
                        image_obj = ProductImageCreate(
                            url=img_url,
                            is_main=(j == 0)
                        )
                        images.append(image_obj)
                        self.logger.info(f"📸 Создан объект изображения {j+1}: {img_url} (главное: {j == 0})")
                    except Exception as e:
                        self.logger.error(f"📸 Ошибка создания объекта изображения для {img_url}: {e}")

                # Логируем финальный результат
                self.logger.info(f"📸 ИТОГО создано объектов изображений: {len(images)}")

                if not images:
                    # Если нет изображений, добавляем заглушку
                    self.logger.warning(f"📸 Нет валидных изображений, добавляем заглушку")
                    placeholder_url = "https://bunkerdoors.ru/images/no-photo.jpg"
                    images = [ProductImageCreate(
                        url=placeholder_url,
                        is_main=True
                    )]
                    self.logger.info(f"📸 Добавлена заглушка: {placeholder_url}")

                # Сохраняем первое изображение для каталога
                if not first_product_image and images and images[0].url != "https://bunkerdoors.ru/images/no-photo.jpg":
                    first_product_image = images[0].url
                    try:
                        await self.update_catalog_image(db, catalog, first_product_image)
                        self.logger.info(f"📸 Обновлено изображение каталога: {first_product_image}")
                    except Exception as e:
                        self.logger.error(f"📸 Ошибка обновления изображения каталога: {e}")
                
                # Генерируем slug
                product_slug = generate_slug(product_data['name'])

                base_description = product_data['description'] or f"Входная дверь {product_data['name']} от Бункер"

                self.logger.info(f"📝 Базовое описание ({len(base_description)} символов): {base_description[:150]}...")
                self.logger.info(f"📝 Характеристик для добавления: {len(product_data['characteristics'])}")

                # Формируем итоговое описание
                description_parts = [base_description]

                # Добавляем характеристики в описание ТОЛЬКО если они есть
                if product_data['characteristics']:
                    characteristics_text = []
                    
                    self.logger.info(f"📝 Добавляем характеристики в описание:")
                    for key, value in product_data['characteristics'].items():
                        if key and value and len(str(key).strip()) > 0 and len(str(value).strip()) > 0:
                            char_line = f"• {str(key).strip()}: {str(value).strip()}"
                            characteristics_text.append(char_line)
                            self.logger.info(f"📝   {char_line}")
                    
                    if characteristics_text:
                        char_section = "\n\n📋 Технические характеристики:\n" + "\n".join(characteristics_text)
                        description_parts.append(char_section)
                        self.logger.info(f"📝 ✅ Добавлена секция характеристик ({len(char_section)} символов)")
                    else:
                        self.logger.warning(f"📝 ❌ Характеристики пусты после фильтрации")
                else:
                    self.logger.warning(f"📝 ❌ Нет характеристик для добавления")

                # Объединяем все части
                description = "\n".join(description_parts)

                self.logger.info(f"📝 ИТОГОВОЕ ОПИСАНИЕ ({len(description)} символов):")
                self.logger.info(f"📝 {description[:300]}..." if len(description) > 300 else f"📝 {description}")

                # Создаем мета-описание
                meta_description = self.create_meta_description(
                    product_data['description'], 
                    product_data['characteristics']
                )
                
                # Создаем объект продукта
                product = ProductCreate(
                    name=product_data['name'],
                    price=product_data['price'],
                    discount_price=product_data['old_price'] if product_data['old_price'] > 0 else None,
                    description=description,  # Полное описание с характеристиками
                    catalog_id=catalog_id,
                    images=images,  # ← Передаем список объектов ProductImageCreate
                    image=images[0].url if images else None,  # ← Главное изображение
                    in_stock=product_data['in_stock'],
                    slug=product_slug,
                    meta_title=product_data['meta_title'] or f"{product_data['name']} - Бункер",
                    meta_description=meta_description[:500],
                    brand_id=brand_id,
                    article=product_data['article']
                )
                
                products.append(product)
                self.logger.info(f"📸 Создан продукт с {len(product.images)} изображениями: {product.name}, цена: {product.price}")
                
            except Exception as e:
                self.logger.error(f"Ошибка при обработке товара {product_url}: {e}", exc_info=True)
        
        self.logger.info(f"Успешно обработано {len(products)} товаров из каталога")
        return products
    
    # ВАЖНО: Метод parse_multiple_catalogs должен быть на ПРАВИЛЬНОМ уровне отступов!
    async def parse_multiple_catalogs(self, catalog_urls: List[str], db: AsyncSession) -> int:
        """
        Парсит несколько каталогов (ПЕРЕОПРЕДЕЛЕН метод из BaseScraper)
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
        """Обычная версия проверки URL изображения"""
        if not url or not isinstance(url, str):
            return False
        
        url = url.strip()
        url_lower = url.lower()
        
        # Исключаем папки (URL заканчивающиеся на /)
        if url.endswith('/'):
            return False
        
        # Исключаем SVG заглушки
        if 'data:image/svg+xml' in url:
            return False
        
        # Проверяем расширение
        valid_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
        has_extension = any(url_lower.endswith(ext) for ext in valid_extensions)
        
        # Проверяем паттерны
        has_images_path = '/images/' in url_lower
        
        # Исключения
        excluded_patterns = ['no-photo', 'placeholder', 'icon', 'logo', 'thumb', 'sprite']
        is_excluded = any(pattern in url_lower for pattern in excluded_patterns)
        
        # Минимальная длина
        is_long_enough = len(url) > 20
        
        return (has_extension or has_images_path) and not is_excluded and is_long_enough
    
    async def assign_product_to_all_categories(self, db: AsyncSession, product_id: int, 
                                             default_category_id: int, category_matches: List[Dict]):
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