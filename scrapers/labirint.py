"""
Скрапер для сайта Лабиринт Двери
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

logger = logging.getLogger("labirint_scraper")

class LabirintScraper(BaseScraper):
    def __init__(self):
        super().__init__(
            brand_name="Лабиринт",
            brand_slug="labirint",
            base_url="https://labirintdoors.ru",
            logger_name="labirint_scraper"
        )
    
    async def parse_labirint_products(self, catalog_url: str, db: AsyncSession) -> List[ProductCreate]:
        """
        Парсит товары с сайта Лабиринт Двери из указанного каталога
        """
        self.logger.info(f"Запуск парсера для каталога {catalog_url}")
        
        # Нормализация URL
        catalog_url = self.normalize_url(catalog_url)
        
        # Получаем каталог из URL
        catalog_slug = catalog_url.rstrip('/').split('/')[-1]
        
        # Формируем имя каталога
        catalog_name_part = catalog_slug.upper()
        catalog_name = f"Входные двери Лабиринт {catalog_name_part}"
        
        # Получаем или обновляем каталог
        brand_id = await self.ensure_brand_exists(db)
        catalog = await self.get_or_create_catalog(db, catalog_name, catalog_slug, brand_id)
        
        # Проверяем, что каталог создан и имеет ID
        if not catalog or catalog.id is None:
            self.logger.error(f"Не удалось создать каталог для {catalog_url}")
            return []
            
        catalog_id = catalog.id
        self.logger.info(f"Получен каталог с ID: {catalog_id}")
        
        # Получаем HTML страницы
        html_content = self.get_html_content(catalog_url)
        if not html_content:
            return []
            
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Находим все товары на странице
        items = soup.select("ul.products-list-01-list li.products-list-01-item")
        
        products = []
        first_product_image = None  # Для сохранения первого изображения продукта
        
        for item in items:
            try:
                header = item.select_one(".products-list-01-item__header a")
                if not header or not header.get("href"):
                    continue
    
                title = header.get_text(strip=True)
                product_url = self.normalize_url(header.get('href'))
                
                # Получаем HTML страницы товара
                resp_html = self.get_html_content(product_url)
                if not resp_html:
                    continue
                    
                soup = BeautifulSoup(resp_html, 'html.parser')
    
                # Получаем название
                name = soup.select_one(".product-01__title")
                name = name.get_text(strip=True) if name else title
    
                # Получаем цену
                price_elem = soup.select_one(".product-01__price")
                price = self.extract_price_from_text(price_elem.get_text(strip=True)) if price_elem else 0
    
                # Получаем описание
                description_parts = []
                
                size = soup.select_one(".product-01__benefits")
                if size:
                    description_parts.append(clean_text(size.get_text()))
                    
                construction = soup.select_one(".product-01__parameters")
                if construction:
                    description_parts.append(clean_text(construction.get_text()))
                    
                full_desc = soup.select_one(".product-01__description") or soup.select_one(".product-description")
                if full_desc:
                    description_parts.append(clean_text(full_desc.get_text()))
                
                description = " ".join(description_parts).strip()
                
                if not description:
                    description = f"Входная дверь {name} от производителя. Качественная металлическая дверь с надежной защитой."
    
                # Извлекаем характеристики продукта
                characteristics = {}
                specs = soup.select(".product-01__specifications .product-specifications-01__row")
                for spec in specs:
                    spec_name = spec.select_one(".product-specifications-01__caption")
                    spec_value = spec.select_one(".product-specifications-01__value")
                    if spec_name and spec_value:
                        key = clean_text(spec_name.get_text())
                        value = clean_text(spec_value.get_text())
                        characteristics[key] = value
    
                # Получаем изображения
                image_urls = []
                
                # Основные изображения из галереи
                for img in soup.select(".product-gallery-01__list img, .product-gallery-01__stage-item img"):
                    self.add_image_url_if_valid(image_urls, img.get("data-bc-lazy-path") or img.get("src"))
    
                # Изображения из ссылок
                for link in soup.select(".product-gallery-01__stage-item-img-container"):
                    self.add_image_url_if_valid(image_urls, link.get("href"))
    
                # Проверяем изображения из JSON-данных
                for element in soup.select("[index]"):
                    try:
                        index_data = element.get("index")
                        if index_data and isinstance(index_data, str):
                            try:
                                index_obj = json.loads(index_data)
                                if isinstance(index_obj, dict):
                                    for value in index_obj.values():
                                        if isinstance(value, str):
                                            self.add_image_url_if_valid(image_urls, value)
                            except json.JSONDecodeError:
                                # Пропускаем некорректный JSON
                                pass
                    except Exception as e:
                        self.logger.warning(f"Ошибка в JSON: {e}")
    
                # Резервный поиск изображений
                if not image_urls:
                    for img in soup.select(".product-01 img, .product-gallery img, .products-list-01-item__image img"):
                        self.add_image_url_if_valid(image_urls, img.get("src"))
    
                # Если изображения не найдены, добавляем заглушку
                if not image_urls:
                    image_urls = ["https://labirintdoors.ru/images/no-photo.jpg"]
    
                # Если это первый продукт с изображениями, сохраняем его изображение для каталога
                if not first_product_image and image_urls:
                    first_product_image = image_urls[0]
                    await self.update_catalog_image(db, catalog, first_product_image)
    
                # Создаем объекты для изображений
                images = [ProductImageCreate(url=img, is_main=(i == 0)) for i, img in enumerate(image_urls)]
    
                # Генерируем slug для продукта
                product_slug = generate_slug(name)
                
                # Создаем мета-описание
                meta_description = self.create_meta_description(description, characteristics)
                
                # Создаем объект продукта
                product = ProductCreate(
                    name=name,
                    price=price,
                    description=description,
                    catalog_id=catalog_id,  # Передаем обязательный catalog_id вместо catalog_name
                    images=images,
                    image=image_urls[0] if image_urls else None,
                    in_stock=True,
                    characteristics=characteristics,
                    slug=product_slug,
                    meta_title=f"{name}",
                    meta_description=meta_description[:500],
                    brand_id=brand_id
                )
                
                # Логируем успешное создание продукта
                self.logger.info(f"Создан продукт {name} с catalog_id={catalog_id}")
                products.append(product)
    
            except Exception as e:
                self.logger.error(f"Ошибка при обработке товара: {e}", exc_info=True)
    
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
                products = await self.parse_labirint_products(url, db)
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
                            
                            # Собираем текст для анализа и последующей классификации
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