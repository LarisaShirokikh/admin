from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.exceptions import raise_404
from app.crud.posts import get_posts_crud
from app.schemas.posts import (
    Post, PostListItem, PostListResponse, PostSearchParams,
    PostTag, PopularTag, PostViewCreate, PostLikeCreate,
)

router = APIRouter()


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.get("/featured/", response_model=List[PostListItem])
async def get_featured_posts(
    limit: int = Query(default=6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    return await get_posts_crud(db).get_featured_posts(limit=limit)


@router.get("/recent/", response_model=List[PostListItem])
async def get_recent_posts(
    limit: int = Query(default=12, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    return await get_posts_crud(db).get_recent_posts(limit=limit)


@router.get("/pinned/", response_model=List[PostListItem])
async def get_pinned_posts(db: AsyncSession = Depends(get_db)):
    return await get_posts_crud(db).get_pinned_posts()


@router.get("/popular/", response_model=List[PostListItem])
async def get_popular_posts(
    limit: int = Query(default=10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    return await get_posts_crud(db).get_popular_posts(limit=limit)


@router.get("/search/", response_model=PostListResponse)
async def search_posts(
    q: Optional[str] = Query(None, min_length=2),
    tag_slug: Optional[str] = None,
    author_id: Optional[int] = None,
    is_featured: Optional[bool] = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    order_by: str = Query(default="created_at"),
    order_dir: str = Query(default="desc"),
    db: AsyncSession = Depends(get_db),
):
    valid_order_by = {"created_at", "published_at", "views_count", "likes_count", "title"}
    valid_order_dir = {"asc", "desc"}
    if order_by not in valid_order_by:
        order_by = "created_at"
    if order_dir not in valid_order_dir:
        order_dir = "desc"

    params = PostSearchParams(
        q=q, tag_slug=tag_slug, author_id=author_id,
        is_published=True, is_featured=is_featured,
        order_by=order_by, order_dir=order_dir,
    )
    posts, total = await get_posts_crud(db).get_posts(
        skip=(page - 1) * per_page, limit=per_page, search_params=params
    )
    return PostListResponse(
        items=posts, total=total, page=page, per_page=per_page,
        pages=(total + per_page - 1) // per_page,
    )


@router.get("/tags/popular/", response_model=List[PopularTag])
async def get_popular_tags(
    limit: int = Query(default=8, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    return await get_posts_crud(db).get_popular_tags(limit=limit)


@router.get("/tags/{tag_slug}/", response_model=PostListResponse)
async def get_posts_by_tag(
    tag_slug: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    crud = get_posts_crud(db)
    tag = await crud.get_tag_by_slug(tag_slug)
    if not tag:
        raise_404(entity="Tag", id=tag_slug)

    params = PostSearchParams(
        tag_slug=tag_slug, is_published=True,
        order_by="published_at", order_dir="desc",
    )
    posts, total = await crud.get_posts(
        skip=(page - 1) * per_page, limit=per_page, search_params=params
    )
    return PostListResponse(
        items=posts, total=total, page=page, per_page=per_page,
        pages=(total + per_page - 1) // per_page,
    )


@router.get("/{slug}/", response_model=Post)
async def get_post_by_slug(slug: str, db: AsyncSession = Depends(get_db)):
    post = await get_posts_crud(db).get_post_by_slug(slug)
    if not post or not post.is_published:
        raise_404(entity="Post", id=slug)
    return post


@router.post("/{post_id}/view/")
async def track_post_view(
    post_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    crud = get_posts_crud(db)
    post = await crud.get_post(post_id)
    if not post or not post.is_published:
        raise_404(entity="Post", id=post_id)

    await crud.track_view(PostViewCreate(
        post_id=post_id,
        ip_address=_get_client_ip(request),
        user_agent=request.headers.get("User-Agent", ""),
        referer=request.headers.get("Referer", ""),
        session_id=request.headers.get("X-Session-ID", ""),
    ))
    return {"message": "View tracked"}


@router.post("/{post_id}/like/")
async def like_post(
    post_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    crud = get_posts_crud(db)
    post = await crud.get_post(post_id)
    if not post or not post.is_published:
        raise_404(entity="Post", id=post_id)

    like = await crud.add_like(PostLikeCreate(
        post_id=post_id,
        ip_address=_get_client_ip(request),
        session_id=request.headers.get("X-Session-ID", ""),
    ))
    if like:
        return {"message": "Like added", "likes_count": post.likes_count + 1}
    return {"message": "Already liked", "likes_count": post.likes_count}