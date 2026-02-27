from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.dependencies import get_db
from app.core.exceptions import raise_404
from app.models.video import Video

router = APIRouter()


def _serialize_video(video: Video) -> dict:
    return {
        "id": video.id,
        "uuid": video.uuid,
        "title": video.title,
        "description": video.description,
        "url": video.url,
        "thumbnail_url": video.thumbnail_url,
        "duration": video.duration,
        "is_featured": video.is_featured,
        "product": {
            "id": video.product.id,
            "name": video.product.name,
            "slug": video.product.slug,
            "price": float(video.product.price) if video.product.price else None,
            "discount_price": float(video.product.discount_price) if video.product.discount_price else None,
        } if video.product else None,
    }


def _base_video_query():
    return select(Video).options(
        joinedload(Video.product)
    ).where(Video.is_active == True)


@router.get("/")
@router.get("/list")
async def get_videos(
    is_featured: Optional[bool] = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = _base_video_query().order_by(Video.created_at.desc()).limit(limit)
    if is_featured is not None:
        query = query.where(Video.is_featured == is_featured)
    result = await db.execute(query)
    return [_serialize_video(v) for v in result.unique().scalars().all()]


@router.get("/featured")
async def get_featured_videos(
    limit: int = Query(4, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    query = (
        _base_video_query()
        .where(Video.is_featured == True)
        .order_by(Video.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    return [_serialize_video(v) for v in result.unique().scalars().all()]


@router.get("/{uuid}")
async def get_video_by_uuid(
    uuid: str = Path(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        _base_video_query().where(and_(Video.uuid == uuid, Video.is_active == True))
    )
    video = result.unique().scalar_one_or_none()
    if not video:
        raise_404(entity="Video", id=uuid)
    return _serialize_video(video)
