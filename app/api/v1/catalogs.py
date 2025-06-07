# app/api/v1/endpoints/catalogs.py (обновленная версия)
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.schemas.catalog import CatalogCreate, CatalogResponse, CatalogUpdate
from app.crud.catalog import (
    create_catalog, 
    get_catalogs, 
    get_catalog,
    get_catalog_by_slug,
    update_catalog,
    delete_catalog,
    toggle_catalog_status,
    count_catalogs,
    count_active_catalogs,
    search_catalogs,
    get_active_catalogs,
    get_catalogs_by_category,
    get_catalogs_by_brand
)
from app.deps import get_db

# Импорты для защиты
from app.deps.admin_auth import get_current_active_admin, get_current_superuser, check_admin_rate_limit
from app.models.admin import AdminUser

router = APIRouter()

# ========== ЧТЕНИЕ (для всех админов) ==========

@router.get("/", response_model=List[CatalogResponse])
async def list_catalogs(
    request: Request,
    skip: int = Query(0, ge=0, description="Number of catalogs to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of catalogs to return"),
    active_only: bool = Query(False, description="Show only active catalogs"),
    search: Optional[str] = Query(None, description="Search term"),
    category_id: Optional[int] = Query(None, description="Filter by category"),
    brand_id: Optional[int] = Query(None, description="Filter by brand"),
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Получить список каталогов с фильтрацией и поиском
    """
    check_admin_rate_limit(request)
    
    print(f"Admin {current_user.username} accessing catalogs list")
    
    # Применяем фильтры
    if search:
        catalogs = await search_catalogs(db, search, skip=skip, limit=limit)
    elif category_id:
        catalogs = await get_catalogs_by_category(db, category_id, skip=skip, limit=limit)
    elif brand_id:
        catalogs = await get_catalogs_by_brand(db, brand_id, skip=skip, limit=limit)
    elif active_only:
        catalogs = await get_active_catalogs(db, skip=skip, limit=limit)
    else:
        catalogs = await get_catalogs(db, skip=skip, limit=limit)
    
    return catalogs

@router.get("/stats/summary")
async def get_catalogs_stats(
    request: Request,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Статистика по каталогам
    """
    check_admin_rate_limit(request, max_requests=20, window_minutes=1)
    
    total_catalogs = await count_catalogs(db)
    active_catalogs = await count_active_catalogs(db)
    inactive_catalogs = total_catalogs - active_catalogs
    
    stats = {
        "total_catalogs": total_catalogs,
        "active_catalogs": active_catalogs,
        "inactive_catalogs": inactive_catalogs,
        "last_updated": "2025-06-07T09:00:00Z",
        "requested_by": current_user.username,
        "user_role": "superuser" if current_user.is_superuser else "admin"
    }
    
    print(f"Admin {current_user.username} requested catalogs statistics")
    return stats

@router.get("/{catalog_id}", response_model=CatalogResponse)
async def get_catalog_by_id(
    request: Request,
    catalog_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Получить каталог по ID
    """
    check_admin_rate_limit(request)
    
    catalog = await get_catalog(db, catalog_id)
    if not catalog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Catalog with id {catalog_id} not found"
        )
    
    print(f"Admin {current_user.username} viewed catalog {catalog_id}")
    return catalog

@router.get("/slug/{slug}", response_model=CatalogResponse)
async def get_catalog_by_slug_endpoint(
    request: Request,
    slug: str,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Получить каталог по slug
    """
    check_admin_rate_limit(request)
    
    catalog = await get_catalog_by_slug(db, slug)
    if not catalog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Catalog with slug '{slug}' not found"
        )
    
    return catalog

# ========== СОЗДАНИЕ И ИЗМЕНЕНИЕ (для всех админов) ==========

@router.post("/", response_model=CatalogResponse, status_code=status.HTTP_201_CREATED)
async def create_catalog_endpoint(
    request: Request,
    catalog_data: CatalogCreate,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Создать новый каталог
    """
    check_admin_rate_limit(request, max_requests=20, window_minutes=1)
    
    # Проверяем уникальность slug если указан
    if catalog_data.slug:
        existing_catalog = await get_catalog_by_slug(db, catalog_data.slug)
        if existing_catalog:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Catalog with slug '{catalog_data.slug}' already exists"
            )
    
    try:
        # Логируем действие админа
        print(f"Admin {current_user.username} creating catalog: {catalog_data.name}")
        
        catalog = await create_catalog(db, catalog_data)
        
        print(f"SUCCESS: Catalog '{catalog.name}' created with ID {catalog.id}")
        return catalog
        
    except Exception as e:
        print(f"ERROR: Failed to create catalog by {current_user.username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error creating catalog: {str(e)}"
        )

@router.put("/{catalog_id}", response_model=CatalogResponse)
async def update_catalog_endpoint(
    request: Request,
    catalog_id: int,
    catalog_data: CatalogUpdate,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Обновить каталог по ID
    """
    check_admin_rate_limit(request, max_requests=30, window_minutes=1)
    
    # Проверяем существование каталога
    existing_catalog = await get_catalog(db, catalog_id)
    if not existing_catalog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Catalog with id {catalog_id} not found"
        )
    
    # Проверяем уникальность slug если он изменился
    if catalog_data.slug and catalog_data.slug != existing_catalog.slug:
        catalog_with_slug = await get_catalog_by_slug(db, catalog_data.slug)
        if catalog_with_slug:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Catalog with slug '{catalog_data.slug}' already exists"
            )
    
    try:
        # Логируем действие админа
        print(f"Admin {current_user.username} updating catalog {catalog_id} ('{existing_catalog.name}')")
        
        updated_catalog = await update_catalog(db, catalog_id, catalog_data)
        if not updated_catalog:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update catalog"
            )
        
        print(f"SUCCESS: Catalog {catalog_id} updated by {current_user.username}")
        return updated_catalog
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR: Failed to update catalog {catalog_id} by {current_user.username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error updating catalog: {str(e)}"
        )

@router.patch("/{catalog_id}", response_model=CatalogResponse)
async def partial_update_catalog(
    request: Request,
    catalog_id: int,
    catalog_data: CatalogUpdate,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Частично обновить каталог по ID
    """
    return await update_catalog_endpoint(request, catalog_id, catalog_data, current_user, db)

@router.post("/{catalog_id}/toggle-status", response_model=CatalogResponse)
async def toggle_catalog_status_endpoint(
    request: Request,
    catalog_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Переключить статус активности каталога
    """
    check_admin_rate_limit(request, max_requests=50, window_minutes=1)
    
    catalog = await get_catalog(db, catalog_id)
    if not catalog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Catalog with id {catalog_id} not found"
        )
    
    # Логируем действие
    new_status = not catalog.is_active
    print(f"Admin {current_user.username} toggling catalog {catalog_id} status to {new_status}")
    
    updated_catalog = await toggle_catalog_status(db, catalog_id)
    if not updated_catalog:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to toggle catalog status"
        )
    
    return updated_catalog

# ========== УДАЛЕНИЕ (только для суперадмина) ==========

@router.delete("/{catalog_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_catalog_endpoint(
    request: Request,
    catalog_id: int,
    current_user: AdminUser = Depends(get_current_superuser),  # Только суперадмин!
    db: AsyncSession = Depends(get_db)
):
    """
    Удалить каталог по ID (только для суперадмина)
    """
    check_admin_rate_limit(request, max_requests=10, window_minutes=1)
    
    # Получаем каталог для логирования
    catalog = await get_catalog(db, catalog_id)
    if not catalog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Catalog with id {catalog_id} not found"
        )
    
    # Критическое действие - подробное логирование
    print(f"CRITICAL: Superuser {current_user.username} deleting catalog {catalog_id} ('{catalog.name}')")
    
    success = await delete_catalog(db, catalog_id)
    if not success:
        print(f"ERROR: Failed to delete catalog {catalog_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete catalog"
        )
    
    print(f"SUCCESS: Catalog {catalog_id} ('{catalog.name}') deleted by superuser {current_user.username}")
    return None