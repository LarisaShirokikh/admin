from decimal import Decimal
import json
import logging
import re
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import and_, func, inspect, or_, select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Product, ProductImage
from app.models.catalog import Catalog
from app.models.category import Category
from app.models.brand import Brand
from app.schemas.product import ProductCreate, ProductUpdate
from app.schemas.product_image import ProductImageCreate
from app.utils.text_utils import generate_slug
from sqlalchemy.orm import selectinload

logger = logging.getLogger("crud_product")

# ---------------------- Вспомогательные функции ----------------------

def calculate_product_prices(original_price: float) -> Tuple[float, float]:
    """
    Рассчитывает цены продукта на основе исходной цены.
    
    Args:
        original_price: Исходная цена продукта
        
    Returns:
        Tuple[float, float]: (price, discount_price), где:
        - price - полная цена (+20% к исходной, округленная)
        - discount_price - исходная цена
    """
    discount_price = float(original_price)
    # Увеличиваем на 20% и округляем до целого числа
    price = round(discount_price * 1.2)
    return price, discount_price

async def find_or_create_catalog(db: AsyncSession, catalog_name: str, images=None):
    """
    Находит или создает каталог по имени.
    Полностью обновляет все поля, если каталог уже существует.
    Обрабатывает случаи с дубликатами и конфликтами slug.
    """
    original_slug = generate_slug(catalog_name)
    
    # Шаг 1: Проверяем, существует ли уже каталог с таким slug
    slug_check = await db.execute(select(Catalog).where(Catalog.slug == original_slug))
    existing_by_slug = slug_check.scalar_one_or_none()
    
    # Шаг 2: Ищем каталоги по имени
    result = await db.execute(select(Catalog).where(Catalog.name == catalog_name))
    catalogs_by_name = result.scalars().all()
    
    # Если нашли каталог по имени и по slug - и это один и тот же каталог
    if existing_by_slug and catalogs_by_name and existing_by_slug.id == catalogs_by_name[0].id:
        # Безопасное обновление: слаг не меняется так как он совпадает
        catalog = existing_by_slug
        catalog.name = catalog_name  # Обновляем имя (на всякий случай)
        catalog.is_active = True
        
        # Если есть изображения, обновляем изображение каталога
        if images and len(images) > 0 and hasattr(images[0], 'url'):
            catalog.image = images[0].url
        
        db.add(catalog)
        await db.flush()
        logger.info(f"Обновлен существующий каталог: {catalog_name} (slug остался прежним)")
        return catalog
    
    # Если нашли каталог по имени
    if catalogs_by_name:
        catalog = catalogs_by_name[0]
        
        # Логируем случай дубликатов
        if len(catalogs_by_name) > 1:
            logger.info(f"Найдено несколько каталогов с именем '{catalog_name}', используем первый (ID: {catalog.id})")
        
        # Проверяем, можем ли мы обновить slug
        if not existing_by_slug:
            # Slug свободен, можно обновить
            catalog.slug = original_slug
        else:
            # Slug занят другим каталогом, создаем уникальный slug
            catalog.slug = f"{original_slug}-{catalog.id}"
            logger.info(f"Slug '{original_slug}' уже занят, используем '{catalog.slug}'")
        
        catalog.name = catalog_name
        catalog.is_active = True
        
        # Если есть изображения, обновляем изображение каталога
        if images and len(images) > 0 and hasattr(images[0], 'url'):
            catalog.image = images[0].url
        
        db.add(catalog)
        await db.flush()
        logger.info(f"Обновлен существующий каталог: {catalog_name}")
        return catalog
    
    # Если нашли каталог по slug, но не по имени
    if existing_by_slug:
        # Обновляем найденный каталог: меняем имя, но оставляем slug
        catalog = existing_by_slug
        catalog.name = catalog_name
        catalog.is_active = True
        
        # Если есть изображения, обновляем изображение каталога
        if images and len(images) > 0 and hasattr(images[0], 'url'):
            catalog.image = images[0].url
        
        db.add(catalog)
        await db.flush()
        logger.info(f"Обновлено имя существующего каталога со slug '{original_slug}'")
        return catalog
    
    # Если не нашли ни по имени, ни по slug, создаем новый
    # Получаем категорию по умолчанию
    default_category_result = await db.execute(
        select(Category).where(Category.slug == "default-category")
    )
    default_category = default_category_result.scalar_one_or_none()
    
    if not default_category:
        # Создаем категорию по умолчанию
        default_category = Category(
            name="Default Category",
            slug="default-category"
        )
        db.add(default_category)
        await db.flush()
    
    # Создаем каталог
    catalog = Catalog(
        name=catalog_name,
        slug=original_slug,
        category_id=default_category.id,
        is_active=True
    )
    
    # Если есть изображения, используем первое для каталога
    if images and len(images) > 0 and hasattr(images[0], 'url'):
        catalog.image = images[0].url
    
    db.add(catalog)
    await db.flush()
    logger.info(f"Создан новый каталог: {catalog_name}")
    
    return catalog

async def format_catalog_name(catalog_name: str) -> str:
    """
    Форматирует имя каталога согласно правилам.
    
    Args:
        catalog_name: Исходное имя каталога
        
    Returns:
        str: Отформатированное имя каталога
    """
    if "Лабиринт" not in catalog_name:
        # Получаем последнее слово из URL
        url_parts = catalog_name.split('/')
        last_part = url_parts[-1] if url_parts else ""
        # Формируем новое имя каталога
        return f"Входные двери Лабиринт {last_part.upper()}"
    return catalog_name

async def generate_product_slug(product_name: str) -> str:
    """
    Генерирует slug для продукта на основе его имени.
    
    Args:
        product_name: Имя продукта
        
    Returns:
        str: Сгенерированный slug
    """
    product_slug = re.sub(r'[^a-zA-Z0-9]', '-', product_name.lower())
    product_slug = re.sub(r'-+', '-', product_slug).strip('-')
    return product_slug

async def manage_product_images(
    db: AsyncSession, 
    product_id: int, 
    new_images: List[Any], 
    existing_images: Optional[List[ProductImage]] = None
) -> None:
    """
    Управляет изображениями продукта - добавляет новые, удаляет отсутствующие.
    """
    logger.info(f"manage_product_images: product_id={product_id}, new_images={len(new_images) if new_images else 0}")
    
    if not new_images:
        logger.warning(f"Нет новых изображений для продукта {product_id}")
        return
    
    # Выводим подробную информацию о новых изображениях
    for i, img_in in enumerate(new_images):
        logger.info(f"Новое изображение {i}: тип={type(img_in)}, есть url={hasattr(img_in, 'url')}")
        if hasattr(img_in, 'url'):
            logger.info(f"URL изображения {i}: {img_in.url}")
        else:
            # Выводим все атрибуты объекта
            logger.info(f"Атрибуты объекта изображения {i}: {dir(img_in)}")
    
    # Если есть существующие изображения
    if existing_images:
        # Собираем URL существующих и новых изображений
        existing_image_urls = [img.url for img in existing_images]
        new_image_urls = []
        
        for img_in in new_images:
            if hasattr(img_in, 'url') and img_in.url:
                new_image_urls.append(img_in.url)
        
        logger.info(f"Существующие URL: {existing_image_urls}")
        logger.info(f"Новые URL: {new_image_urls}")
        
        # Удаляем изображения, которых нет в новом наборе
        for img in existing_images:
            if img.url not in new_image_urls:
                await db.delete(img)
                logger.info(f"Удалено изображение: {img.url}")
        
        # Добавляем только новые изображения
        for idx, img_in in enumerate(new_images):
            if not hasattr(img_in, 'url') or not img_in.url:
                logger.warning(f"Пропущено изображение {idx} - отсутствует URL")
                continue
                
            if img_in.url not in existing_image_urls:
                is_main = (idx == 0 and not any(getattr(img, 'is_main', False) for img in existing_images))
                new_image = ProductImage(
                    product_id=product_id,
                    url=img_in.url,
                    is_main=is_main
                )
                db.add(new_image)
                logger.info(f"Добавлено новое изображение: {img_in.url}, is_main={is_main}")
    else:
        # Добавляем все новые изображения
        for idx, img_in in enumerate(new_images):
            if not hasattr(img_in, 'url') or not img_in.url:
                logger.warning(f"Пропущено изображение {idx} - отсутствует URL")
                continue
                
            new_image = ProductImage(
                product_id=product_id,
                url=img_in.url,
                is_main=(idx == 0)  # Первое изображение будет основным
            )
            db.add(new_image)
            logger.info(f"Добавлено новое изображение: {img_in.url}, is_main={idx == 0}")
    
    # Делаем flush для сохранения изменений
    await db.flush()
    logger.info(f"Сохранены изменения изображений для продукта {product_id}")

# ---------------------- Основные функции CRUD ----------------------

async def get_product_by_title(db: AsyncSession, title: str):
    """Получение продукта по тайтлу"""
    result = await db.execute(
        select(Product).where(Product.title == title)
    )
    return result.scalar_one_or_none()

async def get_all_products(db: AsyncSession):
    
    result = await db.execute(select(Product).options())
    return result.scalars().all()

async def get_product_by_id(db: AsyncSession, product_id: int) -> Optional[Product]:
    """
    Получить продукт по ID с предзагрузкой связанных объектов.
    """
    stmt = (
        select(Product)
        .options(
            selectinload(Product.reviews),
            selectinload(Product.categories)
        )
        .where(Product.id == product_id)
    )
    
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def get_all_products_filtered(
    db: AsyncSession,
    brand_id: Optional[int] = None,
    category_id: Optional[int] = None,
    catalog_id: Optional[int] = None,
    price_from: Optional[float] = None,
    price_to: Optional[float] = None,
) -> List[Product]:
    """
    Получить отфильтрованный список продуктов.
    
    Args:
        db: Сессия базы данных
        brand_id: ID бренда для фильтрации
        category_id: ID категории для фильтрации
        catalog_id: ID каталога для фильтрации
        price_from: Минимальная цена
        price_to: Максимальная цена
        
    Returns:
        List[Product]: Отфильтрованный список продуктов
    """
    # ИСПРАВЛЕНО: Убираем JOIN с Brand, так как может быть не у всех продуктов есть brand
    query = select(Product).join(Catalog).join(Category)

    if catalog_id:
        query = query.where(Product.catalog_id == catalog_id)
    if category_id:
        query = query.where(Catalog.category_id == category_id)
    if brand_id:
        # ИСПРАВЛЕНО: Используем Product.brand_id вместо несуществующего Category.brand_id
        query = query.where(Product.brand_id == brand_id)
    if price_from is not None:
        query = query.where(Product.price >= price_from)
    if price_to is not None:
        query = query.where(Product.price <= price_to)

    result = await db.execute(query)
    return result.scalars().all()

async def create_product(db: AsyncSession, product_data: ProductCreate, auto_commit: bool = False) -> Optional[Product]:
    """
    Создать новый продукт или обновить существующий.
    
    Args:
        db: Сессия базы данных
        product_data: Данные продукта
        auto_commit: Автоматически выполнить commit
        
    Returns:
        Optional[Product]: Созданный или обновленный продукт
    """
    try:
        # Находим или создаем каталог
        catalog = await find_or_create_catalog(db, product_data.catalog_name, product_data.images)

        # Проверяем/генерируем slug для продукта
        product_slug = getattr(product_data, 'slug', None)
        if not product_slug and hasattr(Product, 'slug'):
            product_slug = await generate_product_slug(product_data.name)

        # Проверяем, существует ли продукт
        existing_product_query = select(Product).where(
            Product.name == product_data.name,
            Product.catalog_id == catalog.id
        )
        result = await db.execute(existing_product_query)
        existing_product = result.scalars().first()

        # Рассчитываем цены
        price, discount_price = calculate_product_prices(product_data.price)

        if existing_product:
            # Обновляем существующий продукт
            logger.info(f"Обновление существующего продукта '{product_data.name}' (ID: {existing_product.id})")
            existing_product.description = product_data.description
            existing_product.discount_price = discount_price
            existing_product.price = price
            existing_product.in_stock = product_data.in_stock
            
            # Обновляем slug, если он был создан
            if hasattr(existing_product, 'slug') and product_slug:
                existing_product.slug = product_slug

            # Управляем изображениями продукта
            current_images_query = select(ProductImage).where(ProductImage.product_id == existing_product.id)
            result = await db.execute(current_images_query)
            current_images = result.scalars().all()

            if not (current_images and not product_data.images):
                await manage_product_images(db, existing_product.id, product_data.images, current_images)

            if auto_commit:
                await db.commit()
                await db.refresh(existing_product)
            return existing_product

        # Создаем новый продукт
        product_args = {
            "name": product_data.name,
            "description": product_data.description,
            "discount_price": discount_price,
            "price": price,
            "in_stock": product_data.in_stock,
            "catalog_id": catalog.id
        }
        
        # Добавляем slug, если он необходим
        if hasattr(Product, 'slug') and product_slug:
            product_args["slug"] = product_slug

        new_product = Product(**product_args)

        db.add(new_product)
        await db.flush()

        # Добавляем изображения для нового продукта
        await manage_product_images(db, new_product.id, product_data.images)

        if auto_commit:
            await db.commit()
            await db.refresh(new_product)
        return new_product

    except Exception as e:
        logger.error(f"Ошибка при создании продукта: {e}", exc_info=True)
        await db.rollback()
        raise

async def create_or_update_product(db: AsyncSession, product_in: ProductCreate) -> Optional[Product]:
    """
    Создает новый продукт или обновляет существующий на основе ProductCreate
    
    Args:
        db: Асинхронная сессия базы данных
        product_in: Данные для создания/обновления продукта
        
    Returns:
        Созданный или обновленный продукт
    """
    import logging
    logger = logging.getLogger("product_crud")
    
    try:
        # Проверяем, есть ли catalog_id
        if product_in.catalog_id is None:
            logger.error(f"catalog_id не может быть None для продукта {product_in.name}")
            return None
        
        # Генерируем slug, если его нет
        if not hasattr(product_in, 'slug') or not product_in.slug:
            from app.utils.text_utils import generate_slug
            product_slug = generate_slug(product_in.name)
            # Динамически добавляем атрибут slug к объекту product_in
            setattr(product_in, 'slug', product_slug)
            logger.info(f"Сгенерирован slug: {product_slug} для продукта: {product_in.name}")
        price, discount_price = calculate_product_prices(product_in.price)
            
        # Проверяем существование продукта по slug или имени
        result = await db.execute(
            select(Product).where(
                or_(
                    func.lower(Product.name) == product_in.name.lower()
                )
            )
        )
        
        # Только после генерации slug добавляем условие поиска по slug
        if hasattr(product_in, 'slug') and product_in.slug:
            result = await db.execute(
                select(Product).where(
                    or_(
                        Product.slug == product_in.slug,
                        func.lower(Product.name) == product_in.name.lower()
                    )
                )
            )
        
        existing_product = result.scalar_one_or_none()
        
        # Логируем данные для отладки
        logger.info(f"Create/Update product: {product_in.name}, slug: {getattr(product_in, 'slug', 'No slug')}, catalog_id: {product_in.catalog_id}")
        
        if existing_product:
            # Обновляем существующий продукт
            logger.info(f"Обновление существующего продукта: {existing_product.id}")
            
            # Обновляем поля продукта
            existing_product.name = product_in.name
            existing_product.description = product_in.description
            existing_product.price = price  
            existing_product.discount_price = discount_price 
            existing_product.catalog_id = product_in.catalog_id
            existing_product.brand_id = product_in.brand_id
            existing_product.in_stock = product_in.in_stock
            
            # Обновляем slug только если он есть
            if hasattr(product_in, 'slug') and product_in.slug:
                existing_product.slug = product_in.slug
                
            # Обновляем мета-данные, если они есть
            if hasattr(product_in, 'meta_title') and product_in.meta_title:
                existing_product.meta_title = product_in.meta_title
                
            if hasattr(product_in, 'meta_description') and product_in.meta_description:
                existing_product.meta_description = product_in.meta_description
            
            # Обновляем изображения, если есть
            if product_in.images:
                try:
                    await update_product_images(db, existing_product.id, product_in.images)
                except Exception as e:
                    logger.error(f"Ошибка при обновлении изображений: {str(e)}")
            
            db.add(existing_product)
            await db.flush()
            
            return existing_product
        else:
            # Создаем новый продукт
            logger.info(f"Создание нового продукта, catalog_id: {product_in.catalog_id}")
            
            # Создаем словарь с данными продукта
            product_data = {}
            
            # Копируем только существующие атрибуты
            for field in [
                "name", "price", "description", "catalog_id", "brand_id", 
                "in_stock", "meta_title", "meta_description", 
                "rating"
            ]:
                if hasattr(product_in, field):
                    product_data[field] = getattr(product_in, field)

            product_data["price"] = price
            product_data["discount_price"] = discount_price
            
            # Убеждаемся, что slug существует
            if hasattr(product_in, 'slug') and product_in.slug:
                product_data["slug"] = product_in.slug
            
            # Создаем новый продукт
            new_product = Product(**product_data)
            db.add(new_product)
            await db.flush()
            
            # Добавляем изображения, если есть
            if product_in.images:
                try:
                    await create_product_images(db, new_product.id, product_in.images)
                except Exception as e:
                    logger.error(f"Ошибка при создании изображений: {str(e)}")
            
            return new_product
            
    except Exception as e:
        logger.error(f"Ошибка при создании/обновлении продукта: {e}", exc_info=True)
        await db.rollback()
        raise
        
    return None

# Вспомогательные функции для работы с изображениями

async def create_product_images(db: AsyncSession, product_id: int, images: List[ProductImageCreate]) -> None:
    """Создает изображения для продукта"""
    from app.models.product_image import ProductImage
    
    for image in images:
        db.add(ProductImage(
            product_id=product_id,
            url=image.url,
            is_main=image.is_main
        ))
    
    await db.flush()

async def update_product_images(db: AsyncSession, product_id: int, new_images: List[ProductImageCreate]) -> None:
    """Обновляет изображения продукта"""
    from app.models.product_image import ProductImage
    
    # Удаляем существующие изображения
    stmt = delete(ProductImage).where(ProductImage.product_id == product_id)
    await db.execute(stmt)
    
    # Создаем новые изображения
    await create_product_images(db, product_id, new_images)

async def update_product(db: AsyncSession, product_id: int, product_update: "ProductUpdate") -> Optional[Product]:
    """
    Обновить продукт по ID (частичное обновление).
    
    Args:
        db: Сессия базы данных
        product_id: ID продукта
        product_update: Данные для обновления (только указанные поля)
        
    Returns:
        Optional[Product]: Обновленный продукт или None, если не найден
    """
    try:
        # Получаем существующий продукт
        stmt = (
            select(Product)
            .options(
                selectinload(Product.product_images),
                selectinload(Product.brand),
                selectinload(Product.catalog),
                selectinload(Product.categories)
            )
            .where(Product.id == product_id)
        )
        result = await db.execute(stmt)
        product = result.scalar_one_or_none()
        
        if not product:
            logger.warning(f"Продукт с ID {product_id} не найден")
            return None
        
        # Получаем только те поля, которые были переданы для обновления
        update_data = product_update.model_dump(exclude_unset=True)
        
        logger.info(f"Обновление продукта {product_id} с данными: {update_data}")
        
        # Обновляем только переданные поля
        for field, value in update_data.items():
            if field == 'images':
                # Обработка изображений отдельно
                if value is not None:
                    await update_product_images(db, product_id, value)
                continue
            elif field == 'category_ids':
                # Обработка категорий отдельно
                if value is not None:
                    await update_product_categories(db, product_id, value)
                continue
            elif field == 'price' and value is not None:
                # Если обновляется price, пересчитываем discount_price если она не указана явно
                if 'discount_price' not in update_data:
                    new_price, new_discount_price = calculate_product_prices(value)
                    product.price = new_price
                    product.discount_price = new_discount_price
                else:
                    product.price = value
                continue
            
            # Обновляем обычные поля
            if hasattr(product, field) and value is not None:
                setattr(product, field, value)
        
        # Генерируем slug, если имя изменилось, но slug не указан
        if 'name' in update_data and 'slug' not in update_data and hasattr(product, 'slug'):
            from app.utils.text_utils import generate_slug
            new_slug = generate_slug(update_data['name'])
            
            # Проверяем уникальность slug
            existing_slug_check = await db.execute(
                select(Product.id).where(
                    Product.slug == new_slug,
                    Product.id != product_id
                )
            )
            if not existing_slug_check.scalar_one_or_none():
                product.slug = new_slug
            else:
                # Добавляем ID к slug для уникальности
                product.slug = f"{new_slug}-{product_id}"
        
        db.add(product)
        await db.flush()
        await db.refresh(product)
        
        logger.info(f"Продукт {product_id} успешно обновлен")
        return product
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении продукта {product_id}: {e}", exc_info=True)
        await db.rollback()
        raise

async def delete_product(db: AsyncSession, product_id: int) -> bool:
    """
    Удалить продукт по ID.
    
    Args:
        db: Сессия базы данных
        product_id: ID продукта
        
    Returns:
        bool: True если продукт был удален, False если не найден
    """
    try:
        product = await get_product_by_id(db, product_id)
        if not product:
            return False
        
        # Удаляем связанные изображения
        await db.execute(delete(ProductImage).where(ProductImage.product_id == product_id))
        
        # Удаляем сам продукт
        await db.delete(product)
        await db.flush()
        
        logger.info(f"Продукт {product_id} успешно удален")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при удалении продукта {product_id}: {e}", exc_info=True)
        await db.rollback()
        raise

async def soft_delete_product(db: AsyncSession, product_id: int) -> Optional[Product]:
    """
    Мягкое удаление продукта (установка is_active = False).
    
    Args:
        db: Сессия базы данных
        product_id: ID продукта
        
    Returns:
        Optional[Product]: Обновленный продукт или None, если не найден
    """
    try:
        product = await get_product_by_id(db, product_id)
        if not product:
            return None
        
        product.is_active = False
        db.add(product)
        await db.flush()
        await db.refresh(product)
        
        logger.info(f"Продукт {product_id} мягко удален (is_active = False)")
        return product
        
    except Exception as e:
        logger.error(f"Ошибка при мягком удалении продукта {product_id}: {e}", exc_info=True)
        await db.rollback()
        raise

async def get_products_paginated(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    brand_id: Optional[int] = None,
    catalog_id: Optional[int] = None,
    category_id: Optional[int] = None,
    price_from: Optional[float] = None,
    price_to: Optional[float] = None,
    in_stock: Optional[bool] = None,
    is_active: Optional[bool] = True,
    sort_by: Optional[str] = "created_at",
    sort_order: Optional[str] = "desc"
) -> Tuple[List[Product], int]:
    """
    Получить продукты с пагинацией и фильтрацией.
    
    Returns:
        Tuple[List[Product], int]: (список продуктов, общее количество)
    """
    try:
        # Базовый запрос
        query = select(Product).options(
            selectinload(Product.brand),
            selectinload(Product.catalog),
            selectinload(Product.product_images)
        )
        
        # Применяем фильтры
        filters = []
        
        if is_active is not None:
            filters.append(Product.is_active == is_active)
        
        if brand_id:
            filters.append(Product.brand_id == brand_id)
            
        if catalog_id:
            filters.append(Product.catalog_id == catalog_id)
            
        if price_from is not None:
            filters.append(Product.price >= price_from)
            
        if price_to is not None:
            filters.append(Product.price <= price_to)
            
        if in_stock is not None:
            filters.append(Product.in_stock == in_stock)
        
        if search:
            search_filter = f"%{search}%"
            filters.append(
                or_(
                    Product.name.ilike(search_filter),
                    Product.description.ilike(search_filter)
                )
            )
        
        if filters:
            query = query.where(*filters)
        
        # Сортировка
        if sort_by == "price":
            order_field = Product.price
        elif sort_by == "name":
            order_field = Product.name
        elif sort_by == "rating":
            order_field = Product.rating
        elif sort_by == "created_at":
            order_field = Product.created_at
        else:
            order_field = Product.id
        
        if sort_order == "desc":
            query = query.order_by(order_field.desc())
        else:
            query = query.order_by(order_field.asc())
        
        # Подсчет общего количества
        count_query = select(func.count(Product.id))
        if filters:
            count_query = count_query.where(*filters)
        
        total_result = await db.execute(count_query)
        total_count = total_result.scalar()
        
        # Пагинация
        query = query.offset(skip).limit(limit)
        
        # Выполнение запроса
        result = await db.execute(query)
        products = list(result.scalars().all())
        
        return products, total_count
        
    except Exception as e:
        logger.error(f"Ошибка при получении продуктов с пагинацией: {e}", exc_info=True)
        raise

async def update_product_categories(db: AsyncSession, product_id: int, category_ids: List[int]) -> None:
    """
    Обновить категории продукта.
    
    Args:
        db: Сессия базы данных
        product_id: ID продукта
        category_ids: Список ID категорий
    """
    try:
        # Получаем продукт
        product = await get_product_by_id(db, product_id)
        if not product:
            raise ValueError(f"Продукт с ID {product_id} не найден")
        
        # Получаем категории
        categories_result = await db.execute(
            select(Category).where(Category.id.in_(category_ids))
        )
        categories = list(categories_result.scalars().all())
        
        # Обновляем связи
        product.categories = categories
        db.add(product)
        await db.flush()
        
        logger.info(f"Категории продукта {product_id} обновлены: {category_ids}")
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении категорий продукта {product_id}: {e}", exc_info=True)
        raise

async def get_product_by_slug(db: AsyncSession, slug: str) -> Optional[Product]:
    """
    Получить продукт по slug.
    
    Args:
        db: Сессия базы данных
        slug: Slug продукта
        
    Returns:
        Optional[Product]: Продукт или None, если не найден
    """
    try:
        stmt = (
            select(Product)
            .options(
                selectinload(Product.brand),
                selectinload(Product.catalog),
                selectinload(Product.product_images),
                selectinload(Product.categories),
                selectinload(Product.reviews)
            )
            .where(Product.slug == slug)
        )
        
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
        
    except Exception as e:
        logger.error(f"Ошибка при получении продукта по slug {slug}: {e}", exc_info=True)
        raise

async def get_products_count(
    db: AsyncSession,
    search: Optional[str] = None,
    brand_id: Optional[int] = None,
    catalog_id: Optional[int] = None,
    category_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    in_stock: Optional[bool] = None,
    price_from: Optional[float] = None,
    price_to: Optional[float] = None,
    has_brand: Optional[bool] = None,
    has_catalog: Optional[bool] = None
) -> int:
    """
    Получить количество продуктов с фильтрацией (включая поиск)
    """
    
    query = select(func.count(Product.id))
    conditions = []
    
    # Поиск (тот же код, что и выше)
    if search and search.strip():
        search_term = search.strip()
        search_conditions = []
        
        search_conditions.extend([
            Product.name.ilike(f"%{search_term}%"),
            Product.description.ilike(f"%{search_term}%"),
            Product.brand.has(Brand.name.ilike(f"%{search_term}%")),
            Product.catalog.has(Catalog.name.ilike(f"%{search_term}%")),
            Product.categories.any(Category.name.ilike(f"%{search_term}%"))
        ])
        
        try:
            search_number = float(search_term)
            search_conditions.extend([
                Product.price == search_number,
                Product.discount_price == search_number
            ])
        except ValueError:
            pass
        
        conditions.append(or_(*search_conditions))
    
    # Остальные фильтры
    if brand_id is not None:
        conditions.append(Product.brand_id == brand_id)
    if catalog_id is not None:
        conditions.append(Product.catalog_id == catalog_id)
    if category_id is not None:
        conditions.append(Product.categories.any(Category.id == category_id))
    if is_active is not None:
        conditions.append(Product.is_active == is_active)
    if in_stock is not None:
        # ИСПРАВЛЕНИЕ: Используем in_stock вместо stock_quantity
        conditions.append(Product.in_stock == in_stock)
    if price_from is not None:
        conditions.append(Product.price >= price_from)
    if price_to is not None:
        conditions.append(Product.price <= price_to)
    if has_brand is not None:
        if has_brand:
            conditions.append(Product.brand_id.isnot(None))
        else:
            conditions.append(Product.brand_id.is_(None))
    if has_catalog is not None:
        if has_catalog:
            conditions.append(Product.catalog_id.isnot(None))
        else:
            conditions.append(Product.catalog_id.is_(None))
    
    if conditions:
        query = query.where(and_(*conditions))
    
    result = await db.execute(query)
    return result.scalar() or 0

async def get_products_paginated_with_relations(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    brand_id: Optional[int] = None,
    catalog_id: Optional[int] = None,
    category_id: Optional[int] = None,
    price_from: Optional[float] = None,
    price_to: Optional[float] = None,
    in_stock: Optional[bool] = None,
    is_active: Optional[bool] = True,
    sort_by: str = "created_at",
    sort_order: str = "desc"
):
    """
    Получить продукты с пагинацией, фильтрацией и полными объектами связей
    """
    
    # Базовый запрос с загрузкой связей
    query = select(Product).options(
        selectinload(Product.brand),
        selectinload(Product.catalog),
        selectinload(Product.categories),
        selectinload(Product.product_images)
    )
    
    # Список условий для фильтрации
    conditions = []
    
    # Улучшенный поиск по множественным полям
    if search and search.strip():
        search_term = search.strip()
        
        # Создаем условия для поиска
        search_conditions = []
        
        # Поиск по названию (основной)
        search_conditions.append(
            Product.name.ilike(f"%{search_term}%")
        )
        
        # Поиск по описанию
        search_conditions.append(
            Product.description.ilike(f"%{search_term}%")
        )
        
        
        # Поиск по контенту (если есть)
        # if hasattr(Product, 'content'):
        #     search_conditions.append(
        #         Product.content.ilike(f"%{search_term}%")
        #     )
        
        # Поиск по тегам (если есть)
        if hasattr(Product, 'tags'):
            search_conditions.append(
                func.array_to_string(Product.tags, ' ').ilike(f"%{search_term}%")
            )
        
        # Поиск по бренду (join)
        search_conditions.append(
            Product.brand.has(Brand.name.ilike(f"%{search_term}%"))
        )
        
        # Поиск по каталогу (join)
        search_conditions.append(
            Product.catalog.has(Catalog.name.ilike(f"%{search_term}%"))
        )
        
        # Поиск по категориям (many-to-many)
        search_conditions.append(
            Product.categories.any(Category.name.ilike(f"%{search_term}%"))
        )
        
        # Попытка найти числовое значение для поиска по цене
        try:
            search_number = float(search_term)
            search_conditions.append(Product.price == search_number)
            search_conditions.append(Product.sale_price == search_number)
        except ValueError:
            pass
        
        # Объединяем все условия поиска через OR
        conditions.append(or_(*search_conditions))
    
    # Фильтр по бренду
    if brand_id is not None:
        conditions.append(Product.brand_id == brand_id)
    
    # Фильтр по каталогу
    if catalog_id is not None:
        conditions.append(Product.catalog_id == catalog_id)
    
    # Фильтр по категории
    if category_id is not None:
        conditions.append(Product.categories.any(Category.id == category_id))
    
    # Фильтр по цене
    if price_from is not None:
        conditions.append(Product.price >= price_from)
    if price_to is not None:
        conditions.append(Product.price <= price_to)
    
    # Фильтр по наличию - ИСПРАВЛЕНИЕ
    if in_stock is not None:
        conditions.append(Product.in_stock == in_stock)
    
    # Фильтр по активности
    if is_active is not None:
        conditions.append(Product.is_active == is_active)
    
    # Применяем все условия
    if conditions:
        query = query.where(and_(*conditions))
    
    # Сортировка
    sort_column = getattr(Product, sort_by, Product.created_at)
    if sort_order.lower() == 'desc':
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    
    # Запрос для подсчета общего количества
    count_query = select(func.count(Product.id))
    if conditions:
        count_query = count_query.where(and_(*conditions))
    
    # Выполняем запросы
    total_count_result = await db.execute(count_query)
    total_count = total_count_result.scalar()
    
    # Применяем пагинацию и выполняем основной запрос
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    products = result.scalars().all()
    
    return products, total_count

async def toggle_product_status(db: AsyncSession, product_id: int) -> Optional[Product]:
    """
    Переключить статус активности продукта.
    
    Args:
        db: Сессия базы данных
        product_id: ID продукта
        
    Returns:
        Optional[Product]: Обновленный продукт или None, если не найден
    """
    try:
        product = await get_product_by_id(db, product_id)
        if not product:
            return None
        
        product.is_active = not product.is_active
        db.add(product)
        await db.flush()
        await db.refresh(product)
        
        logger.info(f"Статус продукта {product_id} изменен на: {product.is_active}")
        return product
        
    except Exception as e:
        logger.error(f"Ошибка при переключении статуса продукта {product_id}: {e}", exc_info=True)
        await db.rollback()
        raise

async def get_product_by_id_with_relations(db: AsyncSession, product_id: int) -> Optional[Product]:
    """
    Получить продукт по ID с подгрузкой связанных объектов.
    Связи: Brand, Catalog, Categories (many-to-many), ProductImages, Reviews
    """
    try:
        stmt = (
            select(Product)
            .options(
                selectinload(Product.brand),           # Product.brand_id -> Brand
                selectinload(Product.catalog),         # Product.catalog_id -> Catalog
                selectinload(Product.categories),      # Many-to-many с Category
                selectinload(Product.product_images),  # One-to-many с ProductImage
                selectinload(Product.reviews)          # One-to-many с Review
            )
            .where(Product.id == product_id)
        )
        
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
        
    except Exception as e:
        logger.error(f"Ошибка при получении продукта {product_id} с связями: {e}", exc_info=True)
        raise

async def get_product_by_slug_with_relations(db: AsyncSession, slug: str) -> Optional[Product]:
    """
    Получить продукт по slug с подгрузкой связанных объектов.
    """
    try:
        stmt = (
            select(Product)
            .options(
                selectinload(Product.brand),
                selectinload(Product.catalog),
                selectinload(Product.categories),
                selectinload(Product.product_images),
                selectinload(Product.reviews)
            )
            .where(Product.slug == slug)
        )
        
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
        
    except Exception as e:
        logger.error(f"Ошибка при получении продукта по slug {slug} с связями: {e}", exc_info=True)
        raise

async def update_product_with_relations(db: AsyncSession, product_id: int, product_update: "ProductUpdate") -> Optional[Product]:
    """
    Обновить продукт по ID с возвратом полных связанных объектов.
    """
    try:
        # Сначала обновляем продукт обычной функцией
        updated_product = await update_product(db, product_id, product_update)
        if not updated_product:
            return None
        
        # Затем получаем его с полными связями
        return await get_product_by_id_with_relations(db, product_id)
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении продукта {product_id} с связями: {e}", exc_info=True)
        await db.rollback()
        raise

async def create_product_with_relations(db: AsyncSession, product_data: ProductCreate, auto_commit: bool = False) -> Optional[Product]:
    """
    Создать новый продукт с возвратом полных связанных объектов.
    """
    try:
        # Создаем продукт обычной функцией
        created_product = await create_product(db, product_data, auto_commit=False)
        if not created_product:
            return None
        
        if auto_commit:
            await db.commit()
        
        # Получаем созданный продукт с полными связями
        return await get_product_by_id_with_relations(db, created_product.id)
        
    except Exception as e:
        logger.error(f"Ошибка при создании продукта с связями: {e}", exc_info=True)
        await db.rollback()
        raise

async def get_all_products_filtered_with_relations(
    db: AsyncSession,
    brand_id: Optional[int] = None,
    category_id: Optional[int] = None,
    catalog_id: Optional[int] = None,
    price_from: Optional[float] = None,
    price_to: Optional[float] = None,
) -> List[Product]:
    """
    Получить отфильтрованный список продуктов с подгрузкой связанных объектов.
    """
    try:
        # Используем функцию с пагинацией, но без ограничений
        products, _ = await get_products_paginated_with_relations(
            db=db,
            skip=0,
            limit=10000,  # Большой лимит вместо отсутствия лимита
            brand_id=brand_id,
            category_id=category_id,
            catalog_id=catalog_id,
            price_from=price_from,
            price_to=price_to
        )
        
        return products
        
    except Exception as e:
        logger.error(f"Ошибка при получении отфильтрованных продуктов с связями: {e}", exc_info=True)
        raise

def add_main_image_to_product(product: Product) -> None:
    """
    Добавляет поле main_image к продукту на основе его изображений.
    """
    if hasattr(product, 'product_images') and product.product_images:
        # Ищем изображение помеченное как главное
        main_img = next((img for img in product.product_images if getattr(img, 'is_main', False)), None)
        product.main_image = main_img.url if main_img else product.product_images[0].url
    else:
        product.main_image = None

async def get_all_products_with_relations(db: AsyncSession) -> List[Product]:
    """
    Получить все продукты с подгрузкой связанных объектов.
    ВНИМАНИЕ: Может быть медленной на больших объемах данных!
    """
    try:
        stmt = select(Product).options(
            selectinload(Product.brand),
            selectinload(Product.catalog),
            selectinload(Product.categories),
            selectinload(Product.product_images)
        ).order_by(Product.created_at.desc())
        
        result = await db.execute(stmt)
        products = list(result.scalars().all())
        
        logger.info(f"Получено {len(products)} продуктов с полными связями")
        return products
        
    except Exception as e:
        logger.error(f"Ошибка при получении всех продуктов с связями: {e}", exc_info=True)
        raise

def calculate_new_prices(product, change_type: str, change_value: float, direction: str, price_type: str) -> dict:
    """
    Вычисляет новые цены для товара
    """
    new_prices = {}
    
    def calculate_price(current_price: float) -> float:
        if change_type == "percent":
            multiplier = (100 + change_value) / 100 if direction == "increase" else (100 - change_value) / 100
            return current_price * multiplier
        else:  # fixed
            return current_price + change_value if direction == "increase" else current_price - change_value
    
    if price_type in ['main', 'both'] and product.price:
        new_prices['main'] = Decimal(str(calculate_price(float(product.price)))).quantize(Decimal('0.01'))
    
    if price_type in ['discount', 'both'] and product.discount_price:
        new_prices['discount'] = Decimal(str(calculate_price(float(product.discount_price)))).quantize(Decimal('0.01'))
    
    return new_prices

def validate_prices(prices: dict) -> bool:
    """
    Валидация новых цен
    """
    for price_type, price in prices.items():
        if price is not None:
            if price <= 0:
                return False
            if price > 999999:  # Максимальная цена
                return False
    
    # Проверяем, что цена со скидкой не больше основной
    if prices.get('main') and prices.get('sale'):
        if prices['discount'] >= prices['main']:
            return False
    
    return True

def log_bulk_price_update(user_id: int, request_data: dict, success_count: int, failed_count: int):
    """
    Логирование операции массового изменения цен
    """
    # Здесь можно добавить логирование в БД или файл
    pass