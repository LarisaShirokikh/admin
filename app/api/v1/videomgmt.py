import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import video as video_crud
from app.schemas.video import VideoCreate, VideoResponse, VideoUpdate
from app.core.dependencies import get_db, get_current_active_admin, get_current_superuser, check_admin_rate_limit
from app.core.exceptions import raise_404
from app.models.admin import AdminUser

logger = logging.getLogger(__name__)
router = APIRouter()


# === Upload ===

@router.post("/upload/", response_model=VideoResponse)
async def upload_video(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(""),
    product_title: Optional[str] = Form(None),
    is_featured: bool = Form(False),
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=20, window_minutes=10)

    url = await video_crud.save_upload(file, current_user.username)

    product_id = None
    if product_title:
        product = await video_crud.find_product_by_title(db, product_title)
        if product:
            product_id = product.id

    video = await video_crud.create(db, VideoCreate(
        title=title,
        description=description,
        url=url,
        product_id=product_id,
        is_active=True,
        is_featured=is_featured,
    ))

    if not product_id:
        video = await video_crud.auto_link(db, video.id)

    return video


# === Read ===

@router.get("/", response_model=List[VideoResponse])
async def list_videos(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=1000),
    is_active: Optional[bool] = Query(None),
    is_featured: Optional[bool] = Query(None),
    product_id: Optional[int] = Query(None),
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    return await video_crud.get_all(
        db, skip=skip,
        limit=limit,
        is_active=is_active,
        is_featured=is_featured,
        product_id=product_id
    )


@router.get("/stats/summary")
async def get_stats(
    request: Request,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=20, window_minutes=1)
    stats = await video_crud.get_stats(db)
    stats["upload_stats"] = video_crud.get_upload_stats(current_user.username)
    return stats


@router.get("/featured/", response_model=List[VideoResponse])
async def list_featured(
    request: Request,
    limit: int = Query(10, le=50),
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    return await video_crud.get_featured(db, limit=limit)


@router.get("/search/", response_model=List[VideoResponse])
async def search_videos(
    request: Request,
    q: str = Query(..., min_length=2),
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    return await video_crud.search(db, q)


@router.get("/system-check")
async def system_check(
    request: Request,
    current_user: AdminUser = Depends(get_current_active_admin),
):
    check_admin_rate_limit(request, max_requests=10, window_minutes=1)
    return video_crud.system_check(current_user.username)


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(
    request: Request,
    video_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    video = await video_crud.get_by_id(db, video_id)
    if not video:
        raise_404(entity="Video", id=video_id)
    return video


@router.get("/uuid/{video_uuid}", response_model=VideoResponse)
async def get_video_by_uuid(
    request: Request,
    video_uuid: str,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    video = await video_crud.get_by_uuid(db, video_uuid)
    if not video:
        raise_404(entity="Video", id=video_uuid)
    return video


@router.get("/product/{product_id}", response_model=List[VideoResponse])
async def get_product_videos(
    request: Request,
    product_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    return await video_crud.get_by_product(db, product_id)


@router.get("/{video_id}/suggest-products")
async def suggest_products(
    request: Request,
    video_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    video = await video_crud.get_by_id(db, video_id)
    if not video:
        raise_404(entity="Video", id=video_id)
    suggestions = await video_crud.suggest_products(db, video.title)
    return {
        "video_id": video_id,
        "video_title": video.title,
        "suggestions": [
            {"product_id": p.id, "product_name": p.name, "score": round(s * 100, 1)}
            for p, s in suggestions
        ],
    }


# === Update ===

@router.put("/{video_id}", response_model=VideoResponse)
async def update_video(
    request: Request,
    video_id: int,
    video_data: VideoUpdate,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=30, window_minutes=1)
    result = await video_crud.update(db, video_id, video_data)
    if not result:
        raise_404(entity="Video", id=video_id)
    return result


@router.post("/{video_id}/toggle-status", response_model=VideoResponse)
async def toggle_status(
    request: Request,
    video_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    result = await video_crud.toggle_status(db, video_id)
    if not result:
        raise_404(entity="Video", id=video_id)
    return result


@router.post("/{video_id}/toggle-featured", response_model=VideoResponse)
async def toggle_featured(
    request: Request,
    video_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    result = await video_crud.toggle_featured(db, video_id)
    if not result:
        raise_404(entity="Video", id=video_id)
    return result


@router.post("/{video_id}/auto-link-product", response_model=VideoResponse)
async def auto_link_product(
    request: Request,
    video_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=30, window_minutes=1)
    result = await video_crud.auto_link(db, video_id)
    if not result:
        raise_404(entity="Video", id=video_id)
    return result


# === Delete (superuser only) ===

@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(
    request: Request,
    video_id: int,
    current_user: AdminUser = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=10, window_minutes=1)
    success = await video_crud.remove(db, video_id)
    if not success:
        raise_404(entity="Video", id=video_id)


# === Upload management (superuser only) ===

@router.get("/upload-stats/detailed")
async def upload_stats(
    request: Request,
    current_user: AdminUser = Depends(get_current_superuser),
):
    check_admin_rate_limit(request, max_requests=10, window_minutes=1)
    return video_crud.get_upload_stats()


@router.post("/reset-upload-limits")
async def reset_limits(
    request: Request,
    current_user: AdminUser = Depends(get_current_superuser),
):
    check_admin_rate_limit(request, max_requests=3, window_minutes=5)
    old = video_crud.reset_upload_limits()
    return {"message": "Upload limits reset", "old_stats": old, "reset_by": current_user.username}