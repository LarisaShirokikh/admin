"""
Скрапер для сайта Лабиринт Двери
"""
from typing import List
import logging
import json
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
                characteristics_text = []
                specs = soup.select(".product-01__specifications .product-specifications-01__row")
                for spec in specs:
                    spec_name = spec.select_one(".product-specifications-01__caption")
                    spec_value = spec.select_one(".product-specifications-01__value")
                    if spec_name and spec_value:
                        key = clean_text(spec_name.get_text())
                        value = clean_text(spec_value.get_text())
                        characteristics_text.append(f"{key}: {value}")

                # Объединяем описание с характеристиками
                final_description = description
                if characteristics_text:
                    final_description += "\n\nХарактеристики:\n" + "\n".join(characteristics_text)

                if not final_description.strip():
                    final_description = f"Входная дверь {name} от производителя. Качественная металлическая дверь с надежной защитой."
    
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
                meta_description = self.create_meta_description(final_description, None)
                
                # Создаем объект продукта
                product = ProductCreate(
                    name=name,
                    price=price,
                    description=final_description,
                    catalog_id=catalog_id,  # Передаем обязательный catalog_id вместо catalog_name
                    images=images,
                    image=image_urls[0] if image_urls else None,
                    in_stock=True,
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
        
        self.logger.info(f"Запуск парсера для {len(catalog_urls)} каталогов")
        total_products = 0
        new_products = 0
        updated_products = 0
        
        brand_id = await self.ensure_brand_exists(db)
        await self.update_catalogs_brand_id(db, brand_id)
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
        
        products_to_classify = []
        
        for url in catalog_urls:
            try:
                products = await self.parse_labirint_products(url, db)
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
        Подготавливает текст продукта для анализа категорий
        """
        text_parts = []
        
        # Название продукта (самый важный текст)
        if product_in.name:
            text_parts.append(product_in.name)
        
        # Описание
        if product_in.description:
            text_parts.append(product_in.description)
        
        
        # Мета-информация
        if hasattr(product_in, 'meta_title') and product_in.meta_title:
            text_parts.append(product_in.meta_title)
        
        if hasattr(product_in, 'meta_description') and product_in.meta_description:
            text_parts.append(product_in.meta_description)
        
        return " ".join(text_parts)
