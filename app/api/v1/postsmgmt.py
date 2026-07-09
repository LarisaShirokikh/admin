from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_current_active_admin, check_admin_rate_limit
from app.core.exceptions import raise_400, raise_404
from app.crud.posts import get_posts_crud
from app.models.admin import AdminUser
from app.schemas.posts import (
    Post, PostListResponse, PostSearchParams,
    PostCreate, PostUpdate,
    PostAuthor, PostAuthorCreate,
    PostTag, PostTagCreate,
    PostMedia, PostMediaCreate,
)

router = APIRouter()


@router.get("/", response_model=PostListResponse)
async def list_posts(
    request: Request,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    is_published: Optional[bool] = None,
    is_featured: Optional[bool] = None,
    is_pinned: Optional[bool] = None,
    author_id: Optional[int] = None,
    order_by: str = Query(default="created_at"),
    order_dir: str = Query(default="desc"),
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=100)
    params = PostSearchParams(
        is_published=is_published, is_featured=is_featured,
        is_pinned=is_pinned, author_id=author_id,
        order_by=order_by, order_dir=order_dir,
    )
    posts, total = await get_posts_crud(db).get_posts(
        skip=(page - 1) * per_page, limit=per_page, search_params=params
    )
    return PostListResponse(
        items=posts, total=total, page=page, per_page=per_page,
        pages=(total + per_page - 1) // per_page,
    )


@router.post("/", response_model=Post)
async def create_post(
    request: Request,
    post_data: PostCreate,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=30)
    try:
        return await get_posts_crud(db).create_post(post_data)
    except ValueError as e:
        raise_400(str(e))


@router.get("/{post_id}/", response_model=Post)
async def get_post(
    request: Request,
    post_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    post = await get_posts_crud(db).get_post(post_id)
    if not post:
        raise_404(entity="Post", id=post_id)
    return post


@router.put("/{post_id}/", response_model=Post)
async def update_post(
    request: Request,
    post_id: int,
    post_data: PostUpdate,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=50)
    try:
        post = await get_posts_crud(db).update_post(post_id, post_data)
        if not post:
            raise_404(entity="Post", id=post_id)
        return post
    except ValueError as e:
        raise_400(str(e))


@router.delete("/{post_id}/")
async def delete_post(
    request: Request,
    post_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=20)
    success = await get_posts_crud(db).delete_post(post_id)
    if not success:
        raise_404(entity="Post", id=post_id)
    return {"message": "Post deleted"}


# === Authors ===

@router.post("/authors/", response_model=PostAuthor)
async def create_author(
    request: Request,
    author_data: PostAuthorCreate,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=20)
    return await get_posts_crud(db).create_author(author_data)


@router.get("/authors/{author_id}/", response_model=PostAuthor)
async def get_author(
    request: Request,
    author_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    author = await get_posts_crud(db).get_author(author_id)
    if not author:
        raise_404(entity="Author", id=author_id)
    return author


# === Tags ===

@router.post("/tags/", response_model=PostTag)
async def create_tag(
    request: Request,
    tag_data: PostTagCreate,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=20)
    return await get_posts_crud(db).create_tag(tag_data)


# === Media ===

@router.post("/{post_id}/media/", response_model=PostMedia)
async def create_post_media(
    request: Request,
    post_id: int,
    media_data: PostMediaCreate,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=30)
    crud = get_posts_crud(db)
    post = await crud.get_post(post_id)
    if not post:
        raise_404(entity="Post", id=post_id)
    media_data.post_id = post_id
    return await crud.create_media(media_data)


@router.get("/{post_id}/media/", response_model=List[PostMedia])
async def get_post_media(
    request: Request,
    post_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    return await get_posts_crud(db).get_post_media(post_id)