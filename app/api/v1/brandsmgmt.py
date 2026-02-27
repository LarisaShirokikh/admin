from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.crud import brand as brand_crud
from app.schemas.brand import BrandCreate, BrandResponse, BrandUpdate
from app.core.dependencies import get_db, get_current_active_admin, get_current_superuser, check_admin_rate_limit
from app.core.exceptions import raise_404
from app.models.admin import AdminUser

router = APIRouter()


@router.get("/", response_model=List[BrandResponse])
async def list_brands(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    return await brand_crud.get_brands(db, skip=skip, limit=limit)


@router.get("/{brand_id}", response_model=BrandResponse)
async def get_brand_by_id(
    request: Request,
    brand_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    brand = await brand_crud.get_brand(db, brand_id)
    if not brand:
        raise_404(entity="Brand", id=brand_id)
    return brand


@router.get("/slug/{slug}", response_model=BrandResponse)
async def get_brand_by_slug(
    request: Request,
    slug: str,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    brand = await brand_crud.get_brand_by_slug(db, slug)
    if not brand:
        raise_404(entity="Brand", id=slug)
    return brand


@router.post("/", response_model=BrandResponse, status_code=status.HTTP_201_CREATED)
async def create_brand(
    request: Request,
    brand_data: BrandCreate,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=20, window_minutes=1)
    return await brand_crud.create_brand(db, brand_data)


@router.put("/{brand_id}", response_model=BrandResponse)
async def update_brand(
    request: Request,
    brand_id: int,
    brand_data: BrandUpdate,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=30, window_minutes=1)
    result = await brand_crud.update_brand(db, brand_id, brand_data)
    if not result:
        raise_404(entity="Brand", id=brand_id)
    return result


@router.patch("/{brand_id}", response_model=BrandResponse)
async def partial_update_brand(
    request: Request,
    brand_id: int,
    brand_data: BrandUpdate,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=30, window_minutes=1)
    result = await brand_crud.update_brand(db, brand_id, brand_data)
    if not result:
        raise_404(entity="Brand", id=brand_id)
    return result


@router.post("/{brand_id}/toggle-status", response_model=BrandResponse)
async def toggle_brand_status(
    request: Request,
    brand_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    brand = await brand_crud.get_brand(db, brand_id)
    if not brand:
        raise_404(entity="Brand", id=brand_id)
    return await brand_crud.update_brand(db, brand_id, BrandUpdate(is_active=not brand.is_active))


@router.delete("/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brand(
    request: Request,
    brand_id: int,
    current_user: AdminUser = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=10, window_minutes=1)
    success = await brand_crud.delete_brand(db, brand_id)
    if not success:
        raise_404(entity="Brand", id=brand_id)