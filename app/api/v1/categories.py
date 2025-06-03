# app/api/v1/categories.py (или app/routers/categories.py)
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
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

router = APIRouter()

UPLOAD_DIR = "/app/media/categories"
ALLOWED_EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif", ".webp"]
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

@router.get("/", response_model=List[CategoryResponse])
async def list_categories(db: AsyncSession = Depends(get_db)):
    """Получение списка всех категорий с ID"""
    return await get_categories(db)

@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(category_id: int, db: AsyncSession = Depends(get_db)):
    """Получение категории по ID"""
    category = await get_category_by_id(db, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    return category

@router.post("/", response_model=CategoryResponse)
async def create_cat(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    is_active: bool = Form(True),
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Создание новой категории с обязательным изображением"""
    
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
        
        return await create_category(db, category_data)
        
    except Exception as e:
        # Удаление файла при ошибке создания записи
        delete_image_file(f"/media/categories/{unique_filename}")
        raise HTTPException(status_code=500, detail=f"Ошибка создания категории: {str(e)}")

@router.put("/{category_id}", response_model=CategoryResponse)
async def update_cat(
    category_id: int,
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    is_active: Optional[bool] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db)
):
    """Обновление категории (все поля опциональны)"""
    
    # Проверка существования категории
    category = await get_category_by_id(db, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    
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
        
        return updated_category
        
    except Exception as e:
        # Удаление нового файла при ошибке
        if new_filename:
            delete_image_file(f"/media/categories/{new_filename}")
        raise HTTPException(status_code=500, detail=f"Ошибка обновления категории: {str(e)}")

@router.delete("/{category_id}", response_model=CategoryDeleteResponse)
async def delete_cat(
    category_id: int,
    delete_products: bool = False,  # Флаг для каскадного удаления товаров
    db: AsyncSession = Depends(get_db)
):
    """
    Удаление категории с опциональным каскадным удалением товаров
    
    Args:
        category_id: ID категории для удаления
        delete_products: Если True - удаляет товары, если False - снимает привязку к категории
    """
    
    # Проверка существования категории
    category = await get_category_by_id(db, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    
    try:
        # Проверка наличия товаров в категории
        products = await get_products_by_category_id(db, category_id)
        
        if products:
            if delete_products:
                # Каскадное удаление всех товаров в категории
                await db.execute(delete(Product).where(Product.category_id == category_id))
                print(f"Удалено {len(products)} товаров из категории {category.name}")
            else:
                # Снятие привязки товаров к категории (устанавливаем category_id = None)
                for product in products:
                    product.category_id = None
                await db.flush()
                print(f"Снята привязка к категории для {len(products)} товаров")
        
        # Удаление самой категории
        await delete_category(db, category_id)
        
        # Удаление файла изображения
        if category.image_url:
            delete_image_file(category.image_url)
        
        await db.commit()
        
        return CategoryDeleteResponse(
            message=f"Категория '{category.name}' успешно удалена",
            products_affected=len(products) if products else 0,
            products_deleted=len(products) if delete_products and products else 0,
            products_unlinked=len(products) if not delete_products and products else 0
        )
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка удаления категории: {str(e)}")

@router.get("/{category_id}/products")
async def get_category_products(
    category_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Получение всех товаров в категории"""
    category = await get_category_by_id(db, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    
    products = await get_products_by_category_id(db, category_id)
    
    return {
        "category": category,
        "products_count": len(products),
        "products": products
    }

@router.post("/{category_id}/toggle-status", response_model=CategoryStatusToggleResponse)
async def toggle_category_status(
    category_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Переключение статуса активности категории"""
    category = await get_category_by_id(db, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    
    new_status = not category.is_active
    updated_category = await update_category(db, category_id, {"is_active": new_status})
    
    return CategoryStatusToggleResponse(
        message=f"Статус категории изменен на {'активный' if new_status else 'неактивный'}",
        category=updated_category
    )