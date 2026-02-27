from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.crud import catalog as catalog_crud
from app.schemas.catalog import CatalogCreate, CatalogResponse, CatalogUpdate
from app.core.dependencies import get_db, get_current_active_admin, get_current_superuser, check_admin_rate_limit
from app.core.exceptions import raise_404
from app.models.admin import AdminUser

router = APIRouter()


@router.get("/", response_model=List[CatalogResponse])
async def list_catalogs(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    active_only: bool = Query(False),
    search: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    brand_id: Optional[int] = Query(None),
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    return await catalog_crud.get_catalogs(
        db, skip=skip, limit=limit, active_only=active_only,
        search=search, category_id=category_id, brand_id=brand_id,
    )


@router.get("/stats/summary")
async def get_catalogs_stats(
    request: Request,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=20, window_minutes=1)
    return await catalog_crud.get_stats(db)


@router.get("/{catalog_id}", response_model=CatalogResponse)
async def get_catalog_by_id(
    request: Request,
    catalog_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    catalog = await catalog_crud.get_catalog(db, catalog_id)
    if not catalog:
        raise_404(entity="Catalog", id=catalog_id)
    return catalog


@router.get("/slug/{slug}", response_model=CatalogResponse)
async def get_catalog_by_slug(
    request: Request,
    slug: str,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    catalog = await catalog_crud.get_catalog_by_slug(db, slug)
    if not catalog:
        raise_404(entity="Catalog", id=slug)
    return catalog


@router.post("/", response_model=CatalogResponse, status_code=status.HTTP_201_CREATED)
async def create_catalog(
    request: Request,
    catalog_data: CatalogCreate,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=20, window_minutes=1)
    return await catalog_crud.create_catalog(db, catalog_data)


@router.put("/{catalog_id}", response_model=CatalogResponse)
async def update_catalog(
    request: Request,
    catalog_id: int,
    catalog_data: CatalogUpdate,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=30, window_minutes=1)
    result = await catalog_crud.update_catalog(db, catalog_id, catalog_data)
    if not result:
        raise_404(entity="Catalog", id=catalog_id)
    return result


@router.patch("/{catalog_id}", response_model=CatalogResponse)
async def partial_update_catalog(
    request: Request,
    catalog_id: int,
    catalog_data: CatalogUpdate,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=30, window_minutes=1)
    result = await catalog_crud.update_catalog(db, catalog_id, catalog_data)
    if not result:
        raise_404(entity="Catalog", id=catalog_id)
    return result


@router.post("/{catalog_id}/toggle-status", response_model=CatalogResponse)
async def toggle_catalog_status(
    request: Request,
    catalog_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    result = await catalog_crud.toggle_status(db, catalog_id)
    if not result:
        raise_404(entity="Catalog", id=catalog_id)
    return result


@router.delete("/{catalog_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_catalog(
    request: Request,
    catalog_id: int,
    current_user: AdminUser = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=10, window_minutes=1)
    success = await catalog_crud.delete_catalog(db, catalog_id)
    if not success:
        raise_404(entity="Catalog", id=catalog_id)