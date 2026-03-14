# app/api/v1/bannersmgmt.py

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_db,
    get_current_active_admin,
    check_admin_rate_limit,
)
from app.core.exceptions import raise_400, raise_404
from app.models.admin import AdminUser
from app.crud import banners as crud
from app.schemas.banner import (
    BannerAdminResponse,
    BannerAdminListResponse,
    BannerReorderRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# === GET ===

@router.get("/", response_model=BannerAdminListResponse)
async def list_banners(
    request: Request,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=100)
    banners = await crud.get_all(db)
    return {"items": banners, "total": len(banners)}


@router.get("/{banner_id}", response_model=BannerAdminResponse)
async def get_banner(
    request: Request,
    banner_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    banner = await crud.get_by_id(db, banner_id)
    if not banner:
        raise_404(entity="Banner", id=banner_id)
    return crud._add_is_archived(banner)


# === CREATE ===

@router.post("/", response_model=BannerAdminResponse, status_code=status.HTTP_201_CREATED)
async def create_banner(
    request: Request,
    image: UploadFile = File(...),
    title: Optional[str] = Form(None),
    subtitle: Optional[str] = Form(None),
    href: Optional[str] = Form(None),
    badge: Optional[str] = Form(None),
    text_color: str = Form("light"),
    show_button: bool = Form(True),
    expires_at: Optional[datetime] = Form(None),
    sort_order: int = Form(0),
    is_active: bool = Form(True),
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=30)
    logger.info("Admin %s creating banner", current_user.username)
    try:
        banner = await crud.create(
            db, image,
            title=title, subtitle=subtitle, href=href, badge=badge,
            text_color=text_color, show_button=show_button,
            expires_at=expires_at, sort_order=sort_order, is_active=is_active,
        )
    except ValueError as e:
        raise_400(str(e))
    return crud._add_is_archived(banner)


# === UPDATE ===

@router.put("/{banner_id}", response_model=BannerAdminResponse)
async def update_banner(
    request: Request,
    banner_id: int,
    image: Optional[UploadFile] = File(None),
    title: Optional[str] = Form(None),
    subtitle: Optional[str] = Form(None),
    href: Optional[str] = Form(None),
    badge: Optional[str] = Form(None),
    text_color: Optional[str] = Form(None),
    show_button: Optional[bool] = Form(None),
    expires_at: Optional[datetime] = Form(None),
    clear_expires_at: bool = Form(False),
    sort_order: Optional[int] = Form(None),
    is_active: Optional[bool] = Form(None),
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=30)
    banner = await crud.get_by_id(db, banner_id)
    if not banner:
        raise_404(entity="Banner", id=banner_id)
    try:
        banner = await crud.update(
            db, banner,
            image=image, title=title, subtitle=subtitle, href=href, badge=badge,
            text_color=text_color, show_button=show_button,
            expires_at=expires_at, clear_expires_at=clear_expires_at,
            sort_order=sort_order, is_active=is_active,
        )
    except ValueError as e:
        raise_400(str(e))
    logger.info("Admin %s updated banner %d", current_user.username, banner_id)
    return crud._add_is_archived(banner)


# === TOGGLE / RESTORE ===

@router.post("/{banner_id}/toggle-status", response_model=BannerAdminResponse)
async def toggle_status(
    request: Request,
    banner_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=50)
    banner = await crud.get_by_id(db, banner_id)
    if not banner:
        raise_404(entity="Banner", id=banner_id)
    banner = await crud.toggle_status(db, banner)
    return crud._add_is_archived(banner)


@router.post("/{banner_id}/restore", response_model=BannerAdminResponse)
async def restore_banner(
    request: Request,
    banner_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=20)
    banner = await crud.restore(db, banner_id)
    if not banner:
        raise_404(entity="Banner", id=banner_id)
    logger.info("Admin %s restored banner %d", current_user.username, banner_id)
    return crud._add_is_archived(banner)


# === REORDER ===

@router.patch("/reorder")
async def reorder_banners(
    request: Request,
    data: BannerReorderRequest,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=50)
    items = [{"id": item.id, "sort_order": item.sort_order} for item in data.items]
    count = await crud.reorder(db, items)
    logger.info("Admin %s reordered %d banners", current_user.username, count)
    return {"ok": True, "updated": count}


# === DELETE ===

@router.delete("/{banner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_banner(
    request: Request,
    banner_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=10)
    banner = await crud.get_by_id(db, banner_id)
    if not banner:
        raise_404(entity="Banner", id=banner_id)
    logger.warning("Admin %s deleting banner %d", current_user.username, banner_id)
    await crud.delete(db, banner)