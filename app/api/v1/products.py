# app/api/v1/products.py (защищенная версия)
from datetime import datetime
import shutil
import tempfile
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from sqlalchemy import and_, select
from sqlalchemy.orm import selectinload
from app.models.product_image import ProductImage as ProductImageModel

from app.models.category import Category
from app.models.product import Product
from app.schemas.product import (
    BatchUpdateRequest,
    BatchUpdateResponse,
    PriceUpdateRequest,
    PriceUpdateResponse,
    ProductCountRequest,
    ProductDetail, 
    ProductCreate,
    ProductImage, 
    ProductUpdate,
    ProductListItem,
    ProductFilter,
    ProductResponse,
)
from app.crud.product import (
    calculate_new_prices,
    get_product_by_title,
    delete_product,
    log_bulk_price_update,
    soft_delete_product,
    get_products_count,
    toggle_product_status,
    create_or_update_product,
    # Новые функции с подгрузкой связей
    get_product_by_id_with_relations,
    get_product_by_slug_with_relations,
    get_products_paginated_with_relations,
    get_all_products_filtered_with_relations,
    update_product_with_relations,
    create_product_with_relations,
    validate_prices
)
from app.deps import get_db  # Исправлен импорт
from app.worker.tasks import import_csv_task

# НОВЫЕ ИМПОРТЫ для защиты
from app.deps.admin_auth import get_current_active_admin, get_current_superuser, check_admin_rate_limit
from app.models.admin import AdminUser

router = APIRouter()

# ========== GET эндпоинты (чтение - для всех админов) ==========

@router.get("/", response_model=List[ProductListItem])
async def list_products(
    request: Request,
    skip: int = Query(0, ge=0, description="Количество продуктов для пропуска"),
    limit: int = Query(20, ge=1, le=100, description="Количество продуктов для возврата"),
    search: Optional[str] = Query(None, description="Поиск по названию и описанию"),
    brand_id: Optional[int] = Query(None, description="Фильтр по ID бренда"),
    catalog_id: Optional[int] = Query(None, description="Фильтр по ID каталога"),
    category_id: Optional[int] = Query(None, description="Фильтр по ID категории"),
    price_from: Optional[float] = Query(None, ge=0, description="Минимальная цена"),
    price_to: Optional[float] = Query(None, ge=0, description="Максимальная цена"),
    in_stock: Optional[bool] = Query(None, description="Только товары в наличии"),
    is_active: Optional[bool] = Query(True, description="Только активные товары"),
    sort_by: Optional[str] = Query("created_at", description="Поле для сортировки"),
    sort_order: Optional[str] = Query("desc", description="Порядок сортировки (asc/desc)"),
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """
    Получить список продуктов с пагинацией, фильтрацией и полными объектами брендов/каталогов
    """
    check_admin_rate_limit(request, max_requests=100, window_minutes=1)  # Rate limiting
    
    print(f"Admin {current_user.username} accessing products list (skip={skip}, limit={limit})")
    
    products, total_count = await get_products_paginated_with_relations(
        db=db,
        skip=skip,
        limit=limit,
        search=search,
        brand_id=brand_id,
        catalog_id=catalog_id,
        category_id=category_id,
        price_from=price_from,
        price_to=price_to,
        in_stock=in_stock,
        is_active=is_active,
        sort_by=sort_by,
        sort_order=sort_order
    )
    
    # Добавляем main_image для каждого продукта
    for product in products:
        if hasattr(product, 'product_images') and product.product_images:
            main_img = next((img for img in product.product_images if getattr(img, 'is_main', False)), None)
            product.main_image = main_img.url if main_img else product.product_images[0].url
        else:
            product.main_image = None

        if not hasattr(product, 'categories'):
            # Загружаем категории для продукта
            from sqlalchemy.orm import selectinload
            from app.models.product import Product
            
            result = await db.execute(
                select(Product)
                .options(selectinload(Product.categories))
                .where(Product.id == product.id)
            )
            product_with_categories = result.scalar_one_or_none()
            
            if product_with_categories:
                product.categories = product_with_categories.categories
            else:
                product.categories = []
    
    return products

@router.get("/stats/summary")
async def get_products_stats(
    request: Request,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Статистика по продуктам
    """
    check_admin_rate_limit(request, max_requests=20, window_minutes=1)
    
    # Получаем базовую статистику
    total_products = await get_products_count(db, is_active=None)  # Все продукты
    active_products = await get_products_count(db, is_active=True)
    inactive_products = total_products - active_products
    
    # Дополнительная статистика по брендам и каталогам
    with_brand = await get_products_count(db, has_brand=True)
    without_brand = await get_products_count(db, has_brand=False)
    with_catalog = await get_products_count(db, has_catalog=True)
    without_catalog = await get_products_count(db, has_catalog=False)
    in_stock = await get_products_count(db, in_stock=True)
    out_of_stock = await get_products_count(db, in_stock=False)
    
    stats = {
        "total_products": total_products,
        "active_products": active_products,
        "inactive_products": inactive_products,
        "products_with_brand": with_brand,
        "products_without_brand": without_brand,
        "products_with_catalog": with_catalog,
        "products_without_catalog": without_catalog,
        "products_in_stock": in_stock,
        "products_out_of_stock": out_of_stock,
        "last_updated": "2025-06-08T00:00:00Z",
        "requested_by": current_user.username,
        "user_role": "superuser" if current_user.is_superuser else "admin"
    }
    
    print(f"Admin {current_user.username} requested products statistics")
    return stats

@router.get("/count")
async def get_products_count_endpoint(
    request: Request,
    search: Optional[str] = Query(None, description="Поиск по названию и описанию"),  # Добавлено
    brand_id: Optional[int] = Query(None, description="Фильтр по ID бренда"),
    catalog_id: Optional[int] = Query(None, description="Фильтр по ID каталога"),
    category_id: Optional[int] = Query(None, description="Фильтр по ID категории"),  # Добавлено
    is_active: Optional[bool] = Query(True, description="Только активные товары"),
    in_stock: Optional[bool] = Query(None, description="Фильтр по наличию"),  # Добавлено
    price_from: Optional[float] = Query(None, ge=0, description="Минимальная цена"),  # Добавлено
    price_to: Optional[float] = Query(None, ge=0, description="Максимальная цена"),  # Добавлено
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Получить количество продуктов с фильтрацией (включая поиск)
    """
    check_admin_rate_limit(request)
    
    count = await get_products_count(
        db=db,
        search=search,  # Добавлено
        brand_id=brand_id,
        catalog_id=catalog_id,
        category_id=category_id,  # Добавлено
        is_active=is_active,
        in_stock=in_stock,  # Добавлено
        price_from=price_from,  # Добавлено
        price_to=price_to,  # Добавлено
    )
    return {"count": count}

@router.get("/filter", response_model=List[ProductListItem])
async def filter_products(
    request: Request,  # Добавляем Request
    product_filter: ProductFilter = Depends(),
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """
    Получить отфильтрованный список продуктов с полными объектами брендов/каталогов
    """
    check_admin_rate_limit(request)  # Rate limiting
    
    products = await get_all_products_filtered_with_relations(
        db=db,
        brand_id=product_filter.brand_id,
        category_id=product_filter.category_id,
        catalog_id=product_filter.catalog_id,
        price_from=product_filter.min_price,
        price_to=product_filter.max_price
    )
    
    # Применяем пагинацию
    start = (product_filter.page - 1) * product_filter.per_page
    end = start + product_filter.per_page
    
    # Добавляем main_image для каждого продукта
    for product in products[start:end]:
        if hasattr(product, 'product_images') and product.product_images:
            main_img = next((img for img in product.product_images if getattr(img, 'is_main', False)), None)
            product.main_image = main_img.url if main_img else product.product_images[0].url
        else:
            product.main_image = None
    
    return products[start:end]

@router.get("/by-title/{title}", response_model=ProductDetail)
async def get_product_by_title_route(
    request: Request,  # Добавляем Request
    title: str,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """
    Получить продукт по названию
    """
    check_admin_rate_limit(request)  # Rate limiting
    
    product = await get_product_by_title(db, title)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Продукт с названием '{title}' не найден"
        )
    
    print(f"Admin {current_user.username} viewed product by title: {title}")
    return product

@router.get("/by-slug/{slug}", response_model=ProductDetail)
async def get_product_by_slug_route(
    request: Request,  # Добавляем Request
    slug: str,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """
    Получить продукт по slug с полными объектами брендов, каталогов и категорий
    """
    check_admin_rate_limit(request)  # Rate limiting
    
    product = await get_product_by_slug_with_relations(db, slug)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Продукт с slug '{slug}' не найден"
        )
    
    # Добавляем main_image
    if hasattr(product, 'product_images') and product.product_images:
        main_img = next((img for img in product.product_images if getattr(img, 'is_main', False)), None)
        product.main_image = main_img.url if main_img else product.product_images[0].url
    else:
        product.main_image = None
    
    print(f"Admin {current_user.username} viewed product by slug: {slug}")
    return product

@router.get("/{product_id}", response_model=ProductDetail)
async def get_product(
    request: Request,  # Добавляем Request
    product_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """
    Получить продукт по ID с полными объектами брендов, каталогов и категорий
    """
    check_admin_rate_limit(request)  # Rate limiting
    
    product = await get_product_by_id_with_relations(db, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Продукт с ID {product_id} не найден"
        )
    
    # Добавляем main_image
    if hasattr(product, 'product_images') and product.product_images:
        main_img = next((img for img in product.product_images if getattr(img, 'is_main', False)), None)
        product.main_image = main_img.url if main_img else product.product_images[0].url
    else:
        product.main_image = None
    
    print(f"Admin {current_user.username} viewed product {product_id}")
    return product

@router.get("/{product_id}/images", response_model=List[ProductImage])
async def get_product_images(
    request: Request,
    product_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Получить все изображения продукта по его ID
    """
    check_admin_rate_limit(request)
    
    try:
        # Проверяем существование продукта
        product = await get_product_by_id_with_relations(db, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Продукт с ID {product_id} не найден"
            )
        
        # Получаем изображения из связи product_images (более эффективно)
        if hasattr(product, 'product_images') and product.product_images:
            print(f"Admin {current_user.username} requested images for product {product_id}: {len(product.product_images)} images found")
            return product.product_images
        
        # Если по какой-то причине не загрузились через связь, делаем отдельный запрос
        images_result = await db.execute(
            select(ProductImageModel).where(ProductImageModel.product_id == product_id).order_by(ProductImageModel.is_main.desc(), ProductImageModel.id)
        )
        images = images_result.scalars().all()
        
        print(f"Admin {current_user.username} requested images for product {product_id}: {len(images)} images found")
        return images
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR: Failed to get images for product {product_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при получении изображений: {str(e)}"
        )
# ========== POST эндпоинты (создание - для всех админов) ==========

@router.post("/", response_model=ProductDetail, status_code=status.HTTP_201_CREATED)
async def create_product_endpoint(
    request: Request,  # Добавляем Request
    product: ProductCreate,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """
    Создать новый продукт с возвратом полного объекта со связями
    """
    check_admin_rate_limit(request, max_requests=30, window_minutes=1)  # Rate limiting для создания
    
    try:
        # Логируем действие админа
        print(f"Admin {current_user.username} creating product: {product.name}")
        
        created_product = await create_product_with_relations(db, product, auto_commit=True)
        if not created_product:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Не удалось создать продукт"
            )
        
        # Добавляем main_image
        if hasattr(created_product, 'product_images') and created_product.product_images:
            main_img = next((img for img in created_product.product_images if getattr(img, 'is_main', False)), None)
            created_product.main_image = main_img.url if main_img else created_product.product_images[0].url
        else:
            created_product.main_image = None
        
        print(f"SUCCESS: Product '{created_product.name}' created with ID {created_product.id}")
        return created_product
        
    except Exception as e:
        print(f"ERROR: Failed to create product by {current_user.username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ошибка при создании продукта: {str(e)}"
        )

@router.post("/create-or-update", response_model=ProductDetail)
async def create_or_update_product_endpoint(
    request: Request,  # Добавляем Request
    product: ProductCreate,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """
    Создать новый продукт или обновить существующий с возвратом полного объекта
    """
    check_admin_rate_limit(request, max_requests=30, window_minutes=1)  # Rate limiting
    
    try:
        # Логируем действие админа
        print(f"Admin {current_user.username} creating/updating product: {product.name}")
        
        result_product = await create_or_update_product(db, product)
        if not result_product:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Не удалось создать или обновить продукт"
            )
        await db.commit()
        
        # Получаем продукт с полными связями
        full_product = await get_product_by_id_with_relations(db, result_product.id)
        
        # Добавляем main_image
        if hasattr(full_product, 'product_images') and full_product.product_images:
            main_img = next((img for img in full_product.product_images if getattr(img, 'is_main', False)), None)
            full_product.main_image = main_img.url if main_img else full_product.product_images[0].url
        else:
            full_product.main_image = None
        
        print(f"SUCCESS: Product '{full_product.name}' created/updated with ID {full_product.id}")
        return full_product
        
    except Exception as e:
        await db.rollback()
        print(f"ERROR: Failed to create/update product by {current_user.username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ошибка при создании/обновлении продукта: {str(e)}"
        )

@router.post("/import")
async def import_csv(
    request: Request,  # Добавляем Request
    file: UploadFile = File(...),
    current_user: AdminUser = Depends(get_current_active_admin)  # ЗАЩИТА
):
    """
    Импортировать продукты из CSV-файла
    """
    check_admin_rate_limit(request, max_requests=5, window_minutes=5)  # Строгий лимит для импорта
    
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Файл должен быть в формате CSV"
        )
    
    # Логируем критическое действие импорта
    print(f"IMPORT: Admin {current_user.username} starting CSV import: {file.filename}")
    
    temp = tempfile.NamedTemporaryFile(delete=False)
    try:
        with temp as f:
            shutil.copyfileobj(file.file, f)
        
        import_csv_task.delay(temp.name)
        
        print(f"SUCCESS: CSV import task started by {current_user.username}")
        return {
            "status": "Импорт запущен в фоне", 
            "filename": file.filename,
            "message": "Файл обрабатывается. Проверьте результат через несколько минут.",
            "initiated_by": current_user.username
        }
    except Exception as e:
        print(f"ERROR: CSV import failed for {current_user.username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при загрузке файла: {str(e)}"
        )

@router.post("/{product_id}/toggle-status", response_model=ProductResponse)
async def toggle_product_status_endpoint(
    request: Request,  # Добавляем Request
    product_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """
    Переключить статус активности продукта
    """
    check_admin_rate_limit(request, max_requests=50, window_minutes=1)  # Rate limiting
    
    try:
        # Логируем действие
        print(f"Admin {current_user.username} toggling product {product_id} status")
        
        product = await toggle_product_status(db, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Продукт с ID {product_id} не найден"
            )
        await db.commit()
        
        print(f"SUCCESS: Product {product_id} status toggled by {current_user.username}")
        return product
        
    except Exception as e:
        await db.rollback()
        print(f"ERROR: Failed to toggle product {product_id} status by {current_user.username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ошибка при переключении статуса: {str(e)}"
        )

# ========== PUT/PATCH эндпоинты (обновление - для всех админов) ==========

@router.put("/{product_id}", response_model=ProductDetail)
async def update_product_full(
    request: Request,  # Добавляем Request
    product_id: int,
    product_data: ProductUpdate,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """
    Полное обновление продукта с возвратом полного объекта со связями
    """
    check_admin_rate_limit(request, max_requests=30, window_minutes=1)  # Rate limiting
    
    try:
        # Проверяем существование продукта
        existing_product = await get_product_by_id_with_relations(db, product_id)
        if not existing_product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Продукт с ID {product_id} не найден"
            )
        
        # Логируем действие админа
        print(f"Admin {current_user.username} updating product {product_id} ('{existing_product.name}')")
        
        updated_product = await update_product_with_relations(db, product_id, product_data)
        if not updated_product:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Не удалось обновить продукт"
            )
        
        await db.commit()
        
        # Добавляем main_image
        if hasattr(updated_product, 'product_images') and updated_product.product_images:
            main_img = next((img for img in updated_product.product_images if getattr(img, 'is_main', False)), None)
            updated_product.main_image = main_img.url if main_img else updated_product.product_images[0].url
        else:
            updated_product.main_image = None
        
        print(f"SUCCESS: Product {product_id} updated by {current_user.username}")
        return updated_product
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        print(f"ERROR: Failed to update product {product_id} by {current_user.username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ошибка при обновлении продукта: {str(e)}"
        )

@router.patch("/batch", response_model=BatchUpdateResponse)
async def batch_update_products(
    request: Request,
    batch_data: BatchUpdateRequest,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Массовое обновление продуктов - более эффективно чем отдельные запросы
    """
    print(f"🔄 BATCH UPDATE: User {current_user.username}, Products: {len(batch_data.product_ids)}")
    check_admin_rate_limit(request, max_requests=100, window_minutes=1)  # Строже лимит, но один запрос
    
    if len(batch_data.product_ids) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Максимум 100 продуктов за раз"
        )
    
    print(f"Admin {current_user.username} batch updating {len(batch_data.product_ids)} products")
    
    success_count = 0
    failed_count = 0
    updated_products = []
    failed_products = []
    
    # Получаем данные для обновления только заполненные поля
    update_data = batch_data.update_data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не указаны поля для обновления"
        )
    
    try:
        for product_id in batch_data.product_ids:
            try:
                # Проверяем существование продукта
                existing_product = await get_product_by_id_with_relations(db, product_id)
                if not existing_product:
                    failed_products.append({
                        "product_id": product_id,
                        "error": f"Продукт с ID {product_id} не найден"
                    })
                    failed_count += 1
                    continue
                
                # Обновляем продукт
                updated_product = await update_product_with_relations(db, product_id, batch_data.update_data)
                if updated_product:
                    updated_products.append(product_id)
                    success_count += 1
                else:
                    failed_products.append({
                        "product_id": product_id,
                        "error": "Не удалось обновить продукт"
                    })
                    failed_count += 1
                    
            except Exception as e:
                failed_products.append({
                    "product_id": product_id,
                    "error": str(e)
                })
                failed_count += 1
        
        # Коммитим все изменения сразу
        await db.commit()
        
        print(f"Batch update completed: {success_count} success, {failed_count} failed")
        
        return BatchUpdateResponse(
            success_count=success_count,
            failed_count=failed_count,
            updated_products=updated_products,
            failed_products=failed_products
        )
        
    except Exception as e:
        await db.rollback()
        print(f"ERROR: Batch update failed for {current_user.username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при массовом обновлении: {str(e)}"
        )
    
@router.patch("/{product_id}", response_model=ProductDetail)
async def update_product_partial(
    request: Request,  # Добавляем Request
    product_id: int,
    product_data: ProductUpdate,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """
    Частичное обновление продукта с возвратом полного объекта со связями
    """
    check_admin_rate_limit(request, max_requests=200, window_minutes=1)  # Rate limiting
    
    try:
        # Проверяем существование продукта
        existing_product = await get_product_by_id_with_relations(db, product_id)
        if not existing_product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Продукт с ID {product_id} не найден"
            )
        
        # Проверяем, что есть данные для обновления
        update_data = product_data.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Не указаны поля для обновления"
            )
        
        # Логируем действие админа
        print(f"Admin {current_user.username} partially updating product {product_id} ('{existing_product.name}')")
        
        updated_product = await update_product_with_relations(db, product_id, product_data)
        if not updated_product:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Не удалось обновить продукт"
            )
        
        await db.commit()
        
        # Добавляем main_image
        if hasattr(updated_product, 'product_images') and updated_product.product_images:
            main_img = next((img for img in updated_product.product_images if getattr(img, 'is_main', False)), None)
            updated_product.main_image = main_img.url if main_img else updated_product.product_images[0].url
        else:
            updated_product.main_image = None
        
        print(f"SUCCESS: Product {product_id} partially updated by {current_user.username}")
        return updated_product
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        print(f"ERROR: Failed to partially update product {product_id} by {current_user.username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ошибка при частичном обновлении продукта: {str(e)}"
        )

@router.post("/bulk-update-prices", response_model=PriceUpdateResponse)
async def bulk_update_prices(
    request: PriceUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_active_admin),
):
    """
    Массовое изменение цен товаров
    """
    try:
        # Проверяем права доступа
        if not current_user.is_superuser and not current_user.has_permission("edit_products"):
            raise HTTPException(status_code=403, detail="Недостаточно прав")

        # Строим базовый запрос
        query = select(Product).options(selectinload(Product.categories))
        conditions = []
        
        # Применяем фильтры по области
        if request.scope == "brand" and request.scope_id:
            query = query.filter(Product.brand_id == request.scope_id)
        elif request.scope == "category" and request.scope_id:
            query = query.join(Product.categories).filter(Category.id == request.scope_id)
        elif request.scope == "catalog" and request.scope_id:
            query = query.filter(Product.catalog_id == request.scope_id)
        
        # Дополнительные фильтры
        if request.only_active:
            query = query.filter(Product.is_active == True)
        
        if request.only_in_stock:
            query = query.filter(Product.in_stock == True)
            
        # Фильтр по диапазону цен
        if request.price_range:
            if request.price_range.get("from"):
                query = query.filter(Product.price >= request.price_range["from"])
            if request.price_range.get("to"):
                query = query.filter(Product.price <= request.price_range["to"])
        
        if conditions:
            query = query.where(and_(*conditions))

        # Получаем товары для обновления
        result = await db.execute(query)
        products = result.scalars().all()
        
        updated_products = []
        failed_products = []
        total_price_change = 0.0
        
        for product in products:
            try:
                old_prices = {
                    'main': float(product.price) if product.price else 0,
                    'discount': float(product.discount_price) if product.discount_price else 0 
                }
                
                # Вычисляем новые цены
                new_prices = calculate_new_prices(
                    product, 
                    request.change_type, 
                    request.change_value, 
                    request.direction,
                    request.price_type
                )
                
                # Проверяем валидность новых цен
                if not validate_prices(new_prices):
                    failed_products.append({
                        "product_id": product.id,
                        "error": "Некорректная цена после изменения"
                    })
                    continue
                
                # Обновляем цены
                if request.price_type in ['main', 'both'] and new_prices.get('main') is not None:
                    old_main = product.price
                    product.price = new_prices['main']
                    if old_main:
                        total_price_change += float(new_prices['main'] - old_main)
                
                if request.price_type in ['discount', 'both'] and new_prices.get('discount') is not None:  # ИСПРАВЛЕНО
                    old_discount = product.discount_price or 0  # ИСПРАВЛЕНО
                    product.discount_price = new_prices['discount']  # ИСПРАВЛЕНО
                    if old_discount:
                        total_price_change += float(new_prices['discount'] - old_discount)  # ИСПРАВЛЕНО
                
                # Обновляем время изменения
                from datetime import datetime
                product.updated_at = datetime.utcnow()
                
                updated_products.append(product.id)
                
            except Exception as e:
                failed_products.append({
                    "product_id": product.id,
                    "error": str(e)
                })
        
        await db.commit()
        
        # Логируем операцию
        print(f"Bulk price update by {current_user.username}: {len(updated_products)} success, {len(failed_products)} failed")
        
        return PriceUpdateResponse(
            success_count=len(updated_products),
            failed_count=len(failed_products),
            updated_products=updated_products,
            failed_products=failed_products,
            total_price_change=total_price_change
        )
        
    except Exception as e:
        db.rollback()
        print(f"ERROR in bulk_update_prices: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка при обновлении цен: {str(e)}")

@router.post("/count-for-price-update")
async def get_products_count_for_price_update(
    request: ProductCountRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(get_current_active_admin),
):
    """
    Получение количества товаров для оценки изменений - ИСПРАВЛЕННАЯ ВЕРСИЯ
    """
    try:
        # ИСПРАВЛЕНИЕ: Используем async SQLAlchemy
        from sqlalchemy import select, and_, func
        
        # Строим запрос аналогично основной функции
        query = select(func.count(Product.id))
        conditions = []
        
        if request.scope == "brand" and request.scope_id:
            conditions.append(Product.brand_id == request.scope_id)
        elif request.scope == "category" and request.scope_id:
            query = query.select_from(Product).join(Product.categories).where(Category.id == request.scope_id)
        elif request.scope == "catalog" and request.scope_id:
            conditions.append(Product.catalog_id == request.scope_id)
        
        if request.only_active:
            conditions.append(Product.is_active == True)
        
        if request.only_in_stock:
            conditions.append(Product.in_stock == True)
            
        if request.price_range:
            if request.price_range.get("from"):
                conditions.append(Product.price >= request.price_range["from"])
            if request.price_range.get("to"):
                conditions.append(Product.price <= request.price_range["to"])
        
        # Применяем условия
        if conditions:
            query = query.where(and_(*conditions))
        
        # ИСПРАВЛЕНИЕ: Асинхронное выполнение
        result = await db.execute(query)
        count = result.scalar()
        
        return {"count": count or 0}
        
    except Exception as e:
        print(f"ERROR in get_products_count_for_price_update: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка при подсчете товаров: {str(e)}")
# ========== DELETE эндпоинты (удаление - ТОЛЬКО ДЛЯ СУПЕРАДМИНА) ==========

@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_endpoint(
    request: Request,  # Добавляем Request
    product_id: int,
    current_user: AdminUser = Depends(get_current_superuser),  # ТОЛЬКО СУПЕРАДМИН!
    db: AsyncSession = Depends(get_db)
):
    """
    Полное удаление продукта (только для суперадмина)
    """
    check_admin_rate_limit(request, max_requests=10, window_minutes=1)  # Строгий лимит для удаления
    
    try:
        # Получаем продукт для логирования
        existing_product = await get_product_by_id_with_relations(db, product_id)
        if not existing_product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Продукт с ID {product_id} не найден"
            )
        
        # Критическое действие - подробное логирование
        print(f"CRITICAL: Superuser {current_user.username} deleting product {product_id} ('{existing_product.name}')")
        
        success = await delete_product(db, product_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Продукт с ID {product_id} не найден"
            )
        
        await db.commit()
        
        print(f"SUCCESS: Product {product_id} ('{existing_product.name}') deleted by superuser {current_user.username}")
        return None
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        print(f"ERROR: Failed to delete product {product_id} by {current_user.username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ошибка при удалении продукта: {str(e)}"
        )

@router.delete("/{product_id}/soft", response_model=ProductResponse)
async def soft_delete_product_endpoint(
    request: Request,  # Добавляем Request
    product_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),  # Для всех админов
    db: AsyncSession = Depends(get_db)
):
    """
    Мягкое удаление продукта (установка is_active = False)
    """
    check_admin_rate_limit(request, max_requests=30, window_minutes=1)  # Rate limiting
    
    try:
        # Получаем продукт для логирования
        existing_product = await get_product_by_id_with_relations(db, product_id)
        if not existing_product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Продукт с ID {product_id} не найден"
            )
        
        # Логируем мягкое удаление
        print(f"Admin {current_user.username} soft deleting product {product_id} ('{existing_product.name}')")
        
        product = await soft_delete_product(db, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Продукт с ID {product_id} не найден"
            )
        
        await db.commit()
        
        print(f"SUCCESS: Product {product_id} soft deleted by {current_user.username}")
        return product
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        print(f"ERROR: Failed to soft delete product {product_id} by {current_user.username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ошибка при мягком удалении продукта: {str(e)}"
        )