from fastapi import APIRouter, Depends, File, Form, UploadFile, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.schemas.category import CategoryResponse, CategoryDeleteResponse, CategoryStatusToggleResponse
from app.crud import category as category_crud
from app.core.dependencies import get_db, get_current_active_admin, get_current_superuser, check_admin_rate_limit
from app.core.exceptions import raise_404
from app.models.admin import AdminUser

router = APIRouter()


@router.get("/", response_model=List[CategoryResponse])
async def list_categories(
    request: Request,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    return await category_crud.get_all(db)


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(
    request: Request,
    category_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    category = await category_crud.get_by_id(db, category_id)
    if not category:
        raise_404(entity="Category", id=category_id)
    return category


@router.get("/{category_id}/products")
async def get_category_products(
    request: Request,
    category_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    result = await category_crud.get_with_products(db, category_id)
    if not result:
        raise_404(entity="Category", id=category_id)
    return result


@router.post("/", response_model=CategoryResponse)
async def create_cat(
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    is_active: bool = Form(True),
    image: UploadFile = File(...),
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=20, window_minutes=1)
    return await category_crud.create(db, name=name, description=description, is_active=is_active, image=image)


@router.put("/{category_id}", response_model=CategoryResponse)
async def update_cat(
    request: Request,
    category_id: int,
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    is_active: Optional[bool] = Form(None),
    image: Optional[UploadFile] = File(None),
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=30, window_minutes=1)
    result = await category_crud.update(db, category_id, name=name, description=description, is_active=is_active, image=image)
    if not result:
        raise_404(entity="Category", id=category_id)
    return result


@router.post("/{category_id}/toggle-status", response_model=CategoryStatusToggleResponse)
async def toggle_category_status(
    request: Request,
    category_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    result = await category_crud.toggle_status(db, category_id)
    if not result:
        raise_404(entity="Category", id=category_id)
    return result


@router.delete("/{category_id}", response_model=CategoryDeleteResponse)
async def delete_cat(
    request: Request,
    category_id: int,
    delete_products: bool = False,
    current_user: AdminUser = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=10, window_minutes=1)
    result = await category_crud.remove(db, category_id, delete_products=delete_products)
    if not result:
        raise_404(entity="Category", id=category_id)
    return result


@router.get("/stats/summary")
async def get_categories_stats(
    request: Request,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    return await category_crud.get_stats(db)