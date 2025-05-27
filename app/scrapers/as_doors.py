"""
Скрапер для сайта АС-Двери
"""
import json
from typing import List, Dict, Any, Optional
import logging
from bs4 import BeautifulSoup
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.schemas.product import ProductCreate
from app.schemas.product_image import ProductImageCreate
from app.utils.text_utils import generate_slug
from app.crud.product import create_or_update_product
from app.scrapers.base_scraper import BaseScraper

logger = logging.getLogger("as_doors_scraper")

class AsDoorsScraper(BaseScraper):
    def __init__(self):
        super().__init__(
            brand_name="АС-Двери",
            brand_slug="as-doors",
            base_url="https://as-doors.ru",
            logger_name="as_doors_scraper"
        )
    
    async def parse_as_doors_products(self, catalog_url: str, db: AsyncSession) -> List[ProductCreate]:
        """
        Парсит товары с сайта АС-Двери из указанного каталога
        """
        self.logger.info(f"Запуск парсера для каталога {catalog_url}")

        # Нормализация URL
        catalog_url = self.normalize_url(catalog_url)

        # Получаем или создаем каталог
        catalog_slug = catalog_url.rstrip('/').split('/')[-1]
        catalog_name = f"Входные двери АС {catalog_slug.replace('-', ' ').title()}"
        
        # Получаем brand_id и создаем каталог
        brand_id = await self.ensure_brand_exists(db)
        catalog = await self.get_or_create_catalog(db, catalog_name, catalog_slug, brand_id)
        
        # Проверяем, что каталог создан и имеет ID
        if not catalog or catalog.id is None:
            self.logger.error(f"Не удалось создать каталог для {catalog_url}")
            return []
            
        catalog_id = catalog.id
        self.logger.info(f"Получен каталог с ID: {catalog_id}")
        
        # Получаем список продуктов с сайта
        html_content = self.get_html_content(catalog_url)
        if not html_content:
            return []
            
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Находим контейнер с товарами
        selectors = [
            "#content > div > div.row-block > div.colRight > div.list.clear.instock_list.js-prods-wrap",
            "div.list.clear.instock_list",
            "div.list"
        ]
        
        products_container = None
        for selector in selectors:
            products_container = soup.select_one(selector)
            if products_container:
                break
                
        self.logger.info(f"Найден контейнер товаров: {products_container is not None}")
        
        if not products_container:
            return []
            
        # Ищем товары внутри найденного контейнера
        items = products_container.select("div.item4") or products_container.find_all("div", recursive=False)
        self.logger.info(f"Найдено товаров: {len(items)}")

        products = []
        first_product_image = None  # Для сохранения первого изображения продукта для каталога
        
        for item in items:
            try:
                # Получаем ссылку на продукт
                product_link = self.find_product_link(item)
                if not product_link or not product_link.get("href"):
                    continue

                product_url = self.normalize_url(product_link.get('href'))
                self.logger.info(f"Обрабатываем товар по ссылке: {product_url}")
                
                # Получаем предварительные данные из списка товаров
                title_preview = self.get_title_preview(product_link, item)
                price_preview = self.get_price_preview(item)
                
                # Получаем подробные данные со страницы товара
                resp_html = self.get_html_content(product_url)
                if not resp_html:
                    continue
                    
                product_soup = BeautifulSoup(resp_html, 'html.parser')

                # Получаем основные данные товара
                name = self.get_product_name(product_soup, title_preview)
                price = self.get_product_price(product_soup, price_preview)
                description = self.get_product_description(product_soup, name)
                characteristics = self.get_product_characteristics(product_soup)
                
                # Получаем изображения с приоритетом основного изображения
                image_urls, main_image_url = self.get_product_images(product_soup, item)
                
                # Если изображения не найдены, добавляем заглушку
                if not image_urls:
                    image_urls = ["https://as-doors.ru/images/no-photo.jpg"]
                    main_image_url = image_urls[0]
                
                # Обновляем изображение каталога если это первый товар с изображениями
                if not first_product_image and image_urls:
                    first_product_image = image_urls[0]
                    await self.update_catalog_image(db, catalog, first_product_image)
                
                # Создаем объекты для изображений
                images = self.create_image_objects(image_urls, main_image_url)
                
                # Подготавливаем SEO-данные
                product_slug = generate_slug(name)
                meta_description = self.create_meta_description(description, characteristics)
                
                # Создаем объект продукта с обязательным catalog_id
                product = ProductCreate(
                    name=name,
                    price=price,
                    description=description,
                    catalog_id=catalog_id,  # Обязательное поле catalog_id
                    images=images,
                    image=main_image_url or (image_urls[0] if image_urls else None),
                    in_stock=True,
                    characteristics=characteristics,
                    slug=product_slug,
                    meta_title=f"{name} - АС-Двери",
                    meta_description=meta_description[:500],
                    brand_id=brand_id,
                    rating=0
                )
                
                self.logger.info(f"Создан продукт {name} с catalog_id={catalog_id}")
                products.append(product)

            except Exception as e:
                self.logger.error(f"Ошибка при обработке товара: {e}", exc_info=True)

        return products
    
    def find_product_link(self, item):
        """Находит ссылку на товар в элементе списка"""
        return item.select_one("a[href*='/']") or item.select_one("a[href*='onstock']") or item.select_one("a.title")
    
    def get_title_preview(self, product_link, item):
        """Получает предварительное название товара из списка"""
        title_preview = product_link.get_text(strip=True) if product_link else ""
        if not title_preview:
            thumb_elem = item.select_one("div.thumb")
            if thumb_elem:
                title_preview = thumb_elem.get_text(strip=True)
        return title_preview

    def get_price_preview(self, item):
        """Получает предварительную цену товара из списка"""
        price_elem = item.select_one("div.price")
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            return self.extract_price_from_text(price_text)
        return 0

    def get_product_name(self, product_soup, title_preview):
        """Получает название товара со страницы товара"""
        name_elem = product_soup.select_one("h1.title") or product_soup.select_one("div.title")
        return name_elem.get_text(strip=True) if name_elem else title_preview

    def get_product_price(self, product_soup, price_preview):
        """Получает цену товара со страницы товара"""
        detail_price_elem = product_soup.select_one("div.price")
        if detail_price_elem:
            price_text = detail_price_elem.get_text(strip=True)
            return self.extract_price_from_text(price_text) or price_preview
        return price_preview

    def get_product_description(self, product_soup, name):
        """Получает описание товара"""
        from app.utils.text_utils import clean_text
        
        description_parts = []
        
        # Проверяем различные блоки с описанием
        description_elem = product_soup.select_one("div.description") or product_soup.select_one("div.text")
        if description_elem:
            description_parts.append(clean_text(description_elem.get_text()))
        
        # Проверяем характеристики
        specs_block = product_soup.select_one("div.specifications") or product_soup.select_one("div.params")
        if specs_block:
            description_parts.append(clean_text(specs_block.get_text()))
        
        # Объединяем все части описания
        description = " ".join(description_parts).strip()
        
        # Если описание отсутствует, создаем стандартное
        if not description:
            description = f"Дверь {name} от производителя АС-Двери. Качественная дверь, соответствующая всем стандартам."
            
        return description

    def get_product_characteristics(self, product_soup):
        """Получает характеристики товара"""
        from app.utils.text_utils import clean_text
        
        characteristics = {}
        
        # Ищем таблицы или списки с характеристиками
        specs = product_soup.select("div.params tr") or product_soup.select("div.specifications tr") or product_soup.select("ul.params li")
        
        for spec in specs:
            # Для таблиц
            spec_name = spec.select_one("th") or spec.select_one("td:first-child")
            spec_value = spec.select_one("td:last-child")
            
            # Для списков
            if not spec_name and not spec_value and ":" in spec.get_text():
                parts = spec.get_text().split(":", 1)
                if len(parts) == 2:
                    spec_name_text = parts[0]
                    spec_value_text = parts[1]
                    key = clean_text(spec_name_text)
                    value = clean_text(spec_value_text)
                    characteristics[key] = value
                    continue
                    
            if spec_name and spec_value:
                key = clean_text(spec_name.get_text())
                value = clean_text(spec_value.get_text())
                characteristics[key] = value
                
        return characteristics

    def is_valid_product_image(self, image_url):
        """
        Проверяет, является ли изображение действительным изображением продукта,
        а не иконкой или лейблом
        """
        if not image_url:
            return False
            
        # Игнорировать короткие пути, которые обычно указывают на иконки
        if '/images/' in image_url and len(image_url.split('/')[-1]) <= 6:
            return False
            
        # Исключить конкретные иконки, которые известны как не-продуктовые изображения
        known_icons = [
            '/images/30.png',  # Иконка "Скоро в продаже"
            '/images/new.png',  # Иконка "Новинка"
            '/images/sale.png',  # Иконка "Распродажа"
            '/images/hit.png',   # Иконка "Хит продаж"
            '/images/icon',      # Все иконки в папке icon
        ]
        
        for icon in known_icons:
            if icon in image_url:
                return False
                
        # Проверка расширения файла на изображение
        valid_extensions = ['.jpg', '.jpeg', '.png', '.webp']
        has_valid_extension = False
        
        for ext in valid_extensions:
            if image_url.lower().endswith(ext):
                has_valid_extension = True
                break
                
        if not has_valid_extension:
            return False
            
        # Предполагаем, что реальные фотографии продуктов хранятся в определенных папках
        product_folders = [
            '/upload/', 
            '/katalog/', 
            '/product/', 
            '/doors/', 
            '/gallery/'
        ]
        
        # Проверяем, что изображение имеет подходящую структуру URL
        if not any(folder in image_url for folder in product_folders) and '/images/' in image_url:
            # Если это путь с /images/, то проверяем, что в имени файла есть хотя бы 10 символов
            # так как обычно изображения продуктов имеют более длинные имена
            filename = image_url.split('/')[-1]
            if len(filename) < 10:
                return False
                
        return True
    
    def get_product_images(self, product_soup, item):
        """Получает изображения товара с приоритетом основного изображения"""
        image_urls = []
        main_image_url = None
        
        # Ищем основное изображение
        main_image_selectors = [
            "a[rel='group_main'] img", 
            ".thumb:first-child img",
            "a.fancybox img",  # Добавлен селектор для fancybox
            ".product-image img",  # Добавлен селектор для основного изображения продукта
            "img.main-image",      # Добавлен селектор для изображений с классом main-image
        ]
        
        # Перебираем основные селекторы, чтобы найти главное изображение
        for selector in main_image_selectors:
            main_image_elem = product_soup.select_one(selector)
            if main_image_elem:
                main_image_src = main_image_elem.get("data-src") or main_image_elem.get("src")
                if main_image_src:
                    main_image_url = self.normalize_url(main_image_src)
                    # Проверяем, является ли это изображение валидным
                    if self.is_valid_product_image(main_image_url):
                        self.add_image_url_if_valid(image_urls, main_image_src)
                        break  # Найдено валидное основное изображение
        
        # Если основное изображение не найдено, ищем в других местах
        if not main_image_url:
            # Перебираем все изображения в галерее и берем первое валидное
            gallery_images = product_soup.select(".gallery img, .slider img, .thumbs img")
            for img in gallery_images:
                img_src = img.get("data-src") or img.get("src")
                img_url = self.normalize_url(img_src)
                if img_url and self.is_valid_product_image(img_url):
                    main_image_url = img_url
                    self.add_image_url_if_valid(image_urls, img_src)
                    break
        
        # Собираем все остальные изображения
        selectors = [
            ".gallery img, .slider img",  # Галерея
            ".thumbs img, .thumb:not(:first-child) img",  # Миниатюры, кроме первой
            ".image img",  # Другие контейнеры с изображениями
            ".product-images img"  # Дополнительный селектор для изображений
        ]
        
        for selector in selectors:
            for img in product_soup.select(selector):
                img_src = img.get("data-src") or img.get("src")
                img_url = self.normalize_url(img_src)
                # Проверяем, что изображение валидное, прежде чем добавлять его
                if img_url and self.is_valid_product_image(img_url):
                    self.add_image_url_if_valid(image_urls, img_src)
        
        # Остальная логика остается прежней, но с добавлением проверки is_valid_product_image
        # Проверяем, есть ли изображения в элементе списка (preview), если на странице продукта не найдены
        if not image_urls and item:
            # Проверяем изображения предпросмотра из списка товаров
            preview_img = item.select_one(".thumb img") or item.select_one("img")
            if preview_img:
                img_src = preview_img.get("data-src") or preview_img.get("src")
                img_url = self.normalize_url(img_src)
                if img_url and self.is_valid_product_image(img_url):
                    image_urls.append(img_url)
                    if not main_image_url:
                        main_image_url = img_url

        # Проверяем наличие изображений в блоке с дополнительными данными
        additional_selectors = [
            "div.additional-images img",
            "div.product-info-images img",
            "div.variants img",
            "div.carousel-inner img"
        ]

        for selector in additional_selectors:
            for img in product_soup.select(selector):
                img_src = img.get("data-src") or img.get("src")
                img_url = self.normalize_url(img_src)
                if img_url and self.is_valid_product_image(img_url):
                    self.add_image_url_if_valid(image_urls, img_src)

        # Проверяем наличие изображений, загружаемых через JavaScript
        js_image_elements = product_soup.select("[data-image], [data-lazy-src], [data-original]")
        for elem in js_image_elements:
            for attr in ["data-image", "data-lazy-src", "data-original"]:
                img_src = elem.get(attr)
                if img_src:
                    img_url = self.normalize_url(img_src)
                    if img_url and self.is_valid_product_image(img_url):
                        self.add_image_url_if_valid(image_urls, img_src)

        # Удаляем дубликаты и проверяем наличие основного изображения
        image_urls = list(dict.fromkeys(image_urls))  # Удаление дубликатов с сохранением порядка
        if image_urls and not main_image_url:
            main_image_url = image_urls[0]
                
        # Если после всех проверок изображений нет, используем заглушку
        if not image_urls:
            image_urls = ["https://as-doors.ru/images/no-photo.jpg"]
            main_image_url = image_urls[0]
        
        return image_urls, main_image_url
    
    def add_image_url_if_valid(self, image_urls, img_src):
        """Добавляет URL изображения в список, если это валидный URL и он еще не добавлен"""
        if img_src:
            img_url = self.normalize_url(img_src)
            if img_url and img_url not in image_urls and self.is_valid_product_image(img_url):
                image_urls.append(img_url)
                return True
        return False
    
    async def parse_multiple_catalogs(self, catalog_urls: List[str], db: AsyncSession) -> int:
        """
        Парсит несколько каталогов и создает или обновляет продукты в базе данных
        с автоматической категоризацией
        """
        self.logger.info(f"Запуск парсера для {len(catalog_urls)} каталогов")
        total_products = 0
        new_products = 0
        updated_products = 0
        
        # Получаем бренд один раз в начале процесса
        brand_id = await self.ensure_brand_exists(db)
        
        # Обновляем существующие каталоги, чтобы привязать их к бренду
        await self.update_catalogs_brand_id(db, brand_id)
        
        # Получаем или создаем категорию "все двери"
        all_doors_category = await self.get_or_create_default_category(db, brand_id)
        all_doors_category_id = all_doors_category.id
        
        # Собираем продукты для последующей классификации
        products_to_classify = []
        
        for url in catalog_urls:
            try:
                products = await self.parse_as_doors_products(url, db)
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
                            
                            # Собираем текст для анализа и дополнительной классификации
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
                
                # Классифицируем продукты по дополнительным категориям
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