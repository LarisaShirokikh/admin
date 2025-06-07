# app/api/v1/categories.py (защищенная версия)
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Request
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.models.product import Product
from app.schemas.category import CategoryCreate, CategoryResponse, CategoryDeleteResponse, CategoryStatusToggleResponse
from app.crud.category import (
    create_category, get_category_by_id, delete_category, delete_image_file, 
    get_categories, get_products_by_category_id, save_image_file, 
    update_category, validate_image_file
)
from app.deps import get_db
from app.utils.text_utils import generate_seo_meta, generate_slug

# НОВЫЕ ИМПОРТЫ для защиты
from app.deps.admin_auth import get_current_active_admin, get_current_superuser, check_admin_rate_limit
from app.models.admin import AdminUser

router = APIRouter()

UPLOAD_DIR = "/app/media/categories"
ALLOWED_EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif", ".webp"]
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# ========== ЧТЕНИЕ (для всех админов) ==========

@router.get("/", response_model=List[CategoryResponse])
async def list_categories(
    request: Request,  # Добавляем Request
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """Получение списка всех категорий с ID"""
    check_admin_rate_limit(request)  # Rate limiting
    
    print(f"Admin {current_user.username} accessing categories list")
    
    categories = await get_categories(db)
    return categories

@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(
    request: Request,  # Добавляем Request
    category_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """Получение категории по ID"""
    check_admin_rate_limit(request)  # Rate limiting
    
    category = await get_category_by_id(db, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    
    print(f"Admin {current_user.username} viewed category {category_id}")
    return category

@router.get("/{category_id}/products")
async def get_category_products(
    request: Request,  # Добавляем Request
    category_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """Получение всех товаров в категории"""
    check_admin_rate_limit(request)  # Rate limiting
    
    category = await get_category_by_id(db, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    
    products = await get_products_by_category_id(db, category_id)
    
    print(f"Admin {current_user.username} viewed products for category {category_id}")
    
    return {
        "category": category,
        "products_count": len(products),
        "products": products
    }

# ========== СОЗДАНИЕ И ИЗМЕНЕНИЕ (для всех админов) ==========

@router.post("/", response_model=CategoryResponse)
async def create_cat(
    request: Request,  # Добавляем Request
    name: str = Form(...),
    description: Optional[str] = Form(None),
    is_active: bool = Form(True),
    image: UploadFile = File(...),
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """Создание новой категории с обязательным изображением"""
    check_admin_rate_limit(request, max_requests=20, window_minutes=1)  # Rate limiting для создания
    
    # Логируем начало создания
    print(f"Admin {current_user.username} creating category: {name}")
    
    # Валидация и сохранение изображения
    file_ext = validate_image_file(image)
    unique_filename = await save_image_file(image, file_ext)
    
    try:
        # Генерация slug и SEO данных
        slug = generate_slug(name.strip())
        seo_meta = generate_seo_meta(name.strip())
        
        # Подготовка данных для создания
        category_data = {
            "name": name.strip(),
            "slug": slug,
            "description": description.strip() if description else f"Категория товаров: {name.strip()}",
            "image_url": f"/media/categories/{unique_filename}",
            "is_active": is_active,
            "meta_title": seo_meta["meta_title"],
            "meta_description": seo_meta["meta_description"], 
            "meta_keywords": seo_meta["meta_keywords"],
            "product_count": 0
        }
        
        category = await create_category(db, category_data)
        
        print(f"SUCCESS: Category '{category.name}' created with ID {category.id} by {current_user.username}")
        return category
        
    except Exception as e:
        # Удаление файла при ошибке создания записи
        delete_image_file(f"/media/categories/{unique_filename}")
        print(f"ERROR: Failed to create category by {current_user.username}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка создания категории: {str(e)}")

@router.put("/{category_id}", response_model=CategoryResponse)
async def update_cat(
    request: Request,  # Добавляем Request
    category_id: int,
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    is_active: Optional[bool] = Form(None),
    image: Optional[UploadFile] = File(None),
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """Обновление категории (все поля опциональны)"""
    check_admin_rate_limit(request, max_requests=30, window_minutes=1)  # Rate limiting
    
    # Проверка существования категории
    category = await get_category_by_id(db, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    
    # Логируем начало обновления
    print(f"Admin {current_user.username} updating category {category_id} ('{category.name}')")
    
    update_data = {}
    old_image_url = category.image_url
    new_filename = None
    
    try:
        # Обновление изображения если предоставлено
        if image and image.filename:
            file_ext = validate_image_file(image)
            new_filename = await save_image_file(image, file_ext)
            update_data["image_url"] = f"/media/categories/{new_filename}"
        
        # Обновление других полей
        if name is not None:
            update_data["name"] = name.strip()
            # Перегенерация slug и SEO при изменении имени
            update_data["slug"] = generate_slug(name.strip())
            seo_meta = generate_seo_meta(name.strip())
            update_data.update(seo_meta)
        
        if description is not None:
            update_data["description"] = description.strip()
        
        if is_active is not None:
            update_data["is_active"] = is_active
        
        # Обновление записи в БД
        updated_category = await update_category(db, category_id, update_data)
        
        # Удаление старого изображения после успешного обновления
        if new_filename and old_image_url:
            delete_image_file(old_image_url)
        
        print(f"SUCCESS: Category {category_id} updated by {current_user.username}")
        return updated_category
        
    except Exception as e:
        # Удаление нового файла при ошибке
        if new_filename:
            delete_image_file(f"/media/categories/{new_filename}")
        print(f"ERROR: Failed to update category {category_id} by {current_user.username}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка обновления категории: {str(e)}")

@router.post("/{category_id}/toggle-status", response_model=CategoryStatusToggleResponse)
async def toggle_category_status(
    request: Request,  # Добавляем Request
    category_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """Переключение статуса активности категории"""
    check_admin_rate_limit(request, max_requests=50, window_minutes=1)  # Rate limiting
    
    category = await get_category_by_id(db, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    
    new_status = not category.is_active
    
    # Логируем действие
    print(f"Admin {current_user.username} toggling category {category_id} status to {new_status}")
    
    updated_category = await update_category(db, category_id, {"is_active": new_status})
    
    return CategoryStatusToggleResponse(
        message=f"Статус категории изменен на {'активный' if new_status else 'неактивный'}",
        category=updated_category
    )

# ========== УДАЛЕНИЕ (только для суперадмина) ==========

@router.delete("/{category_id}", response_model=CategoryDeleteResponse)
async def delete_cat(
    request: Request,  # Добавляем Request
    category_id: int,
    delete_products: bool = False,  # Флаг для каскадного удаления товаров
    current_user: AdminUser = Depends(get_current_superuser),  # ТОЛЬКО СУПЕРАДМИН!
    db: AsyncSession = Depends(get_db)
):
    """
    Удаление категории с опциональным каскадным удалением товаров
    (только для суперадмина)
    
    Args:
        category_id: ID категории для удаления
        delete_products: Если True - удаляет товары, если False - снимает привязку к категории
    """
    check_admin_rate_limit(request, max_requests=10, window_minutes=1)  # Строгий лимит для удаления
    
    # Проверка существования категории
    category = await get_category_by_id(db, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    
    # Критическое действие - подробное логирование
    print(f"CRITICAL: Superuser {current_user.username} deleting category {category_id} ('{category.name}') with delete_products={delete_products}")
    
    try:
        # Проверка наличия товаров в категории
        products = await get_products_by_category_id(db, category_id)
        
        if products:
            if delete_products:
                # Каскадное удаление всех товаров в категории
                await db.execute(delete(Product).where(Product.category_id == category_id))
                print(f"CRITICAL: Deleted {len(products)} products from category {category.name} by {current_user.username}")
            else:
                # Снятие привязки товаров к категории (устанавливаем category_id = None)
                for product in products:
                    product.category_id = None
                await db.flush()
                print(f"INFO: Unlinked {len(products)} products from category {category.name}")
        
        # Удаление самой категории
        await delete_category(db, category_id)
        
        # Удаление файла изображения
        if category.image_url:
            delete_image_file(category.image_url)
        
        await db.commit()
        
        print(f"SUCCESS: Category {category_id} ('{category.name}') deleted by superuser {current_user.username}")
        
        return CategoryDeleteResponse(
            message=f"Категория '{category.name}' успешно удалена",
            products_affected=len(products) if products else 0,
            products_deleted=len(products) if delete_products and products else 0,
            products_unlinked=len(products) if not delete_products and products else 0
        )
        
    except Exception as e:
        await db.rollback()
        print(f"ERROR: Failed to delete category {category_id} by {current_user.username}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка удаления категории: {str(e)}")

# ========== СТАТИСТИКА (для всех админов) ==========

@router.get("/stats/summary")
async def get_categories_stats(
    request: Request,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Статистика по категориям
    """
    check_admin_rate_limit(request, max_requests=20, window_minutes=1)
    
    # Получаем все категории для подсчета статистики
    all_categories = await get_categories(db)
    
    total_categories = len(all_categories)
    active_categories = len([c for c in all_categories if c.is_active])
    inactive_categories = total_categories - active_categories
    
    # Подсчитываем категории с продуктами
    categories_with_products = 0
    total_products_count = 0
    
    for category in all_categories:
        products = await get_products_by_category_id(db, category.id)
        if products:
            categories_with_products += 1
            total_products_count += len(products)
    
    stats = {
        "total_categories": total_categories,
        "active_categories": active_categories,
        "inactive_categories": inactive_categories,
        "categories_with_products": categories_with_products,
        "empty_categories": total_categories - categories_with_products,
        "total_products_in_categories": total_products_count,
        "average_products_per_category": round(total_products_count / total_categories, 2) if total_categories > 0 else 0,
        "last_updated": "2025-06-07T09:00:00Z",
        "requested_by": current_user.username,
        "user_role": "superuser" if current_user.is_superuser else "admin"
    }
    
    print(f"Admin {current_user.username} requested categories statistics")
    return stats