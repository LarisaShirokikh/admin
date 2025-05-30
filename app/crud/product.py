import json
import logging
import re
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import func, inspect, or_, select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Product, ProductImage
from app.models.catalog import Catalog
from app.models.category import Category
from app.models.brand import Brand
from app.schemas.product import ProductCreate
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
            slug="default-category",
            brand_id=1  # Предполагаем, что бренд с ID 1 существует
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
    """
    Получить все продукты.
    
    Args:
        db: Сессия базы данных
        
    Returns:
        List[Product]: Список всех продуктов
    """
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
    query = select(Product).join(Catalog).join(Category).join(Brand)

    if catalog_id:
        query = query.where(Product.catalog_id == catalog_id)
    if category_id:
        query = query.where(Catalog.category_id == category_id)
    if brand_id:
        query = query.where(Category.brand_id == brand_id)
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
            existing_product.characteristics = product_data.characteristics
            
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
            "catalog_id": catalog.id,
            "characteristics": product_data.characteristics
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
            existing_product.characteristics = product_in.characteristics
            
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
                "in_stock", "characteristics", "meta_title", "meta_description", 
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