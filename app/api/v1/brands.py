# app/api/v1/endpoints/brands.py (обновленная версия с защитой)
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.crud.brand import (
    create_brand, 
    get_brands, 
    get_brand, 
    get_brand_by_slug,
    update_brand, 
    delete_brand
)
from app.schemas.brand import BrandCreate, BrandResponse, BrandUpdate
from app.deps import get_db

# НОВЫЕ ИМПОРТЫ для защиты
from app.deps.admin_auth import get_current_active_admin, get_current_superuser, check_admin_rate_limit
from app.models.admin import AdminUser

router = APIRouter()

@router.get("/", response_model=List[BrandResponse])
async def list_brands(
    request: Request,  # Добавляем Request
    skip: int = Query(0, ge=0, description="Number of brands to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of brands to return"),
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """
    Получить список всех брендов с пагинацией
    """
    check_admin_rate_limit(request)  # Rate limiting
    
    brands = await get_brands(db, skip=skip, limit=limit)
    return brands

@router.get("/{brand_id}", response_model=BrandResponse)
async def get_brand_by_id(
    request: Request,  # Добавляем Request
    brand_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """
    Получить бренд по ID
    """
    check_admin_rate_limit(request)  # Rate limiting
    
    brand = await get_brand(db, brand_id)
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Brand with id {brand_id} not found"
        )
    return brand

@router.get("/slug/{slug}", response_model=BrandResponse)
async def get_brand_by_slug_endpoint(
    request: Request,  # Добавляем Request
    slug: str,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """
    Получить бренд по slug
    """
    check_admin_rate_limit(request)  # Rate limiting
    
    brand = await get_brand_by_slug(db, slug)
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Brand with slug '{slug}' not found"
        )
    return brand

@router.post("/", response_model=BrandResponse, status_code=status.HTTP_201_CREATED)
async def create_brand_endpoint(
    request: Request,  # Добавляем Request
    brand_data: BrandCreate,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """
    Создать новый бренд
    """
    check_admin_rate_limit(request, max_requests=20, window_minutes=1)  # Rate limiting для создания
    
    # Проверяем, не существует ли бренд с таким slug (если slug указан)
    if brand_data.slug:
        existing_brand = await get_brand_by_slug(db, brand_data.slug)
        if existing_brand:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Brand with slug '{brand_data.slug}' already exists"
            )
    
    try:
        # Логируем действие админа
        print(f"Admin {current_user.username} creating brand: {brand_data.name}")
        
        brand = await create_brand(db, brand_data)
        return brand
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error creating brand: {str(e)}"
        )

@router.put("/{brand_id}", response_model=BrandResponse)
async def update_brand_endpoint(
    request: Request,  # Добавляем Request
    brand_id: int,
    brand_data: BrandUpdate,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """
    Обновить бренд по ID
    """
    check_admin_rate_limit(request, max_requests=30, window_minutes=1)  # Rate limiting
    
    # Проверяем, существует ли бренд
    existing_brand = await get_brand(db, brand_id)
    if not existing_brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Brand with id {brand_id} not found"
        )
    
    # Если обновляется slug, проверяем уникальность
    if brand_data.slug and brand_data.slug != existing_brand.slug:
        brand_with_slug = await get_brand_by_slug(db, brand_data.slug)
        if brand_with_slug:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Brand with slug '{brand_data.slug}' already exists"
            )
    
    try:
        # Логируем действие админа
        print(f"Admin {current_user.username} updating brand {brand_id}")
        
        updated_brand = await update_brand(db, brand_id, brand_data)
        return updated_brand
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error updating brand: {str(e)}"
        )

@router.patch("/{brand_id}", response_model=BrandResponse)
async def partial_update_brand(
    request: Request,  # Добавляем Request
    brand_id: int,
    brand_data: BrandUpdate,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """
    Частично обновить бренд по ID (алиас для PUT)
    """
    return await update_brand_endpoint(request, brand_id, brand_data, current_user, db)

@router.delete("/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brand_endpoint(
    request: Request,  # Добавляем Request
    brand_id: int,
    current_user: AdminUser = Depends(get_current_superuser),  # ТОЛЬКО СУПЕРАДМИН!
    db: AsyncSession = Depends(get_db)
):
    """
    Удалить бренд по ID (только для суперадмина)
    """
    check_admin_rate_limit(request, max_requests=10, window_minutes=1)  # Строгий лимит для удаления
    
    # Логируем критическое действие
    print(f"CRITICAL: Superuser {current_user.username} deleting brand {brand_id}")
    
    success = await delete_brand(db, brand_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Brand with id {brand_id} not found"
        )
    return None

@router.post("/{brand_id}/toggle-status", response_model=BrandResponse)
async def toggle_brand_status(
    request: Request,  # Добавляем Request
    brand_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),  # ЗАЩИТА
    db: AsyncSession = Depends(get_db)
):
    """
    Переключить статус активности бренда
    """
    check_admin_rate_limit(request, max_requests=50, window_minutes=1)  # Rate limiting
    
    brand = await get_brand(db, brand_id)
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Brand with id {brand_id} not found"
        )
    
    # Логируем действие
    print(f"Admin {current_user.username} toggling brand {brand_id} status")
    
    # Создаем объект для обновления только статуса
    brand_update = BrandUpdate(is_active=not brand.is_active)
    updated_brand = await update_brand(db, brand_id, brand_update)
    
    return updated_brand