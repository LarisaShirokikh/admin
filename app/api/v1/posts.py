# app/api/v1/posts/router.py

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.database import get_db
from app.crud.posts import get_posts_crud, PostsCRUD
from app.schemas.posts import (
    Post, PostListItem, PostListResponse, PostSearchParams,
    PostTag, PopularTag,
    PostCreate, PostUpdate,
    PostViewCreate, PostLikeCreate,
    PostAuthor, PostAuthorCreate, PostAuthorUpdate,
    PostTagCreate, PostTagUpdate,
    PostMedia, PostMediaCreate, PostMediaUpdate
)

router = APIRouter()


def get_client_ip(request: Request) -> str:
    """Получить IP адрес клиента"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# === ПУБЛИЧНЫЕ ЭНДПОИНТЫ ===

@router.get("/featured/", response_model=List[PostListItem])
async def get_featured_posts(
    limit: int = Query(default=6, ge=1, le=20),
    is_published: bool = Query(default=True),
    db: AsyncSession = Depends(get_db)
):
    """Получить рекомендуемые посты"""
    crud = get_posts_crud(db)
    posts = await crud.get_featured_posts(limit=limit)
    return posts


@router.get("/recent/", response_model=List[PostListItem])
async def get_recent_posts(
    limit: int = Query(default=12, ge=1, le=50),
    is_published: bool = Query(default=True),
    db: AsyncSession = Depends(get_db)
):
    """Получить последние посты"""
    crud = get_posts_crud(db)
    posts = await crud.get_recent_posts(limit=limit)
    return posts


@router.get("/pinned/", response_model=List[PostListItem])
async def get_pinned_posts(
    is_published: bool = Query(default=True),
    db: AsyncSession = Depends(get_db)
):
    """Получить закрепленные посты"""
    crud = get_posts_crud(db)
    posts = await crud.get_pinned_posts()
    return posts


@router.get("/popular/", response_model=List[PostListItem])
async def get_popular_posts(
    limit: int = Query(default=10, ge=1, le=20),
    db: AsyncSession = Depends(get_db)
):
    """Получить популярные посты"""
    crud = get_posts_crud(db)
    posts = await crud.get_popular_posts(limit=limit)
    return posts


@router.get("/search/", response_model=PostListResponse)
async def search_posts(
    q: Optional[str] = Query(None, min_length=2, description="Поисковый запрос"),
    tag_slug: Optional[str] = Query(None, description="Slug тега"),
    author_id: Optional[int] = Query(None, description="ID автора"),
    is_featured: Optional[bool] = Query(None, description="Только рекомендуемые"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    order_by: str = Query(default="created_at", description="Поле для сортировки"),
    order_dir: str = Query(default="desc", description="Направление сортировки"),
    db: AsyncSession = Depends(get_db)
):
    """Поиск постов с фильтрацией"""
    # Валидируем параметры сортировки
    valid_order_by = ['created_at', 'published_at', 'views_count', 'likes_count', 'title']
    valid_order_dir = ['asc', 'desc']
    
    if order_by not in valid_order_by:
        order_by = "created_at"
    if order_dir not in valid_order_dir:
        order_dir = "desc"
    
    crud = get_posts_crud(db)
    
    search_params = PostSearchParams(
        q=q,
        tag_slug=tag_slug,
        author_id=author_id,
        is_published=True,  # Публичный поиск только по опубликованным
        is_featured=is_featured,
        order_by=order_by,
        order_dir=order_dir
    )
    
    skip = (page - 1) * per_page
    posts, total = await crud.get_posts(skip=skip, limit=per_page, search_params=search_params)
    
    return PostListResponse(
        items=posts,
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page
    )


@router.get("/{slug}/", response_model=Post)
async def get_post_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db)
):
    """Получить пост по slug"""
    crud = get_posts_crud(db)
    post = await crud.get_post_by_slug(slug)
    
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")
    
    if not post.is_published:
        raise HTTPException(status_code=404, detail="Пост не опубликован")
    
    return post


@router.post("/{post_id}/view/")
async def track_post_view(
    post_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Отследить просмотр поста"""
    crud = get_posts_crud(db)
    
    # Проверяем существование поста
    post = await crud.get_post(post_id)
    if not post or not post.is_published:
        raise HTTPException(status_code=404, detail="Пост не найден")
    
    # Создаем запись о просмотре
    view_data = PostViewCreate(
        post_id=post_id,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("User-Agent", ""),
        referer=request.headers.get("Referer", ""),
        session_id=request.headers.get("X-Session-ID", "")
    )
    
    await crud.track_view(view_data)
    return {"message": "Просмотр зафиксирован"}


@router.post("/{post_id}/like/")
async def like_post(
    post_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Поставить лайк посту"""
    crud = get_posts_crud(db)
    
    # Проверяем существование поста
    post = await crud.get_post(post_id)
    if not post or not post.is_published:
        raise HTTPException(status_code=404, detail="Пост не найден")
    
    # Создаем лайк
    like_data = PostLikeCreate(
        post_id=post_id,
        ip_address=get_client_ip(request),
        session_id=request.headers.get("X-Session-ID", "")
    )
    
    like = await crud.add_like(like_data)
    if like:
        return {"message": "Лайк добавлен", "likes_count": post.likes_count + 1}
    else:
        return {"message": "Лайк уже был поставлен", "likes_count": post.likes_count}


# === ТЕГИ ===

@router.get("/tags/popular/", response_model=List[PopularTag])
async def get_popular_tags(
    limit: int = Query(default=8, ge=1, le=20),
    db: AsyncSession = Depends(get_db)
):
    """Получить популярные теги"""
    crud = get_posts_crud(db)
    tags = await crud.get_popular_tags(limit=limit)
    return tags


@router.get("/tags/{tag_slug}/", response_model=PostListResponse)
async def get_posts_by_tag(
    tag_slug: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Получить посты по тегу"""
    crud = get_posts_crud(db)
    
    # Проверяем существование тега
    tag = await crud.get_tag_by_slug(tag_slug)
    if not tag:
        raise HTTPException(status_code=404, detail="Тег не найден")
    
    search_params = PostSearchParams(
        tag_slug=tag_slug,
        is_published=True,
        order_by="published_at",
        order_dir="desc"
    )
    
    skip = (page - 1) * per_page
    posts, total = await crud.get_posts(skip=skip, limit=per_page, search_params=search_params)
    
    return PostListResponse(
        items=posts,
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page
    )


# === АДМИНИСТРАТИВНЫЕ ЭНДПОИНТЫ ===
# (Здесь должна быть авторизация, но пока оставляем без неё для тестирования)

@router.get("/", response_model=PostListResponse)
async def list_posts(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(None),
    is_published: Optional[bool] = Query(None),
    is_featured: Optional[bool] = Query(None),
    is_pinned: Optional[bool] = Query(None),
    author_id: Optional[int] = Query(None),
    order_by: str = Query(default="created_at"),
    order_dir: str = Query(default="desc"),
    db: AsyncSession = Depends(get_db)
):
    """Получить список всех постов (административный)"""
    crud = get_posts_crud(db)
    
    search_params = PostSearchParams(
        status=status,
        is_published=is_published,
        is_featured=is_featured,
        is_pinned=is_pinned,
        author_id=author_id,
        order_by=order_by,
        order_dir=order_dir
    )
    
    skip = (page - 1) * per_page
    posts, total = await crud.get_posts(skip=skip, limit=per_page, search_params=search_params)
    
    return PostListResponse(
        items=posts,
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page
    )


@router.post("/", response_model=Post)
async def create_post(
    post_data: PostCreate,
    db: AsyncSession = Depends(get_db)
):
    """Создать новый пост"""
    crud = get_posts_crud(db)
    
    try:
        post = await crud.create_post(post_data)
        return post
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{post_id}/", response_model=Post)
async def get_post(
    post_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Получить пост по ID"""
    crud = get_posts_crud(db)
    post = await crud.get_post(post_id)
    
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")
    
    return post


@router.put("/{post_id}/", response_model=Post)
async def update_post(
    post_id: int,
    post_data: PostUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Обновить пост"""
    crud = get_posts_crud(db)
    
    try:
        post = await crud.update_post(post_id, post_data)
        if not post:
            raise HTTPException(status_code=404, detail="Пост не найден")
        return post
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{post_id}/")
async def delete_post(
    post_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Удалить пост"""
    crud = get_posts_crud(db)
    
    success = await crud.delete_post(post_id)
    if not success:
        raise HTTPException(status_code=404, detail="Пост не найден")
    
    return {"message": "Пост удален"}


# === АВТОРЫ ===

@router.post("/authors/", response_model=PostAuthor)
async def create_author(
    author_data: PostAuthorCreate,
    db: AsyncSession = Depends(get_db)
):
    """Создать автора"""
    crud = get_posts_crud(db)
    author = await crud.create_author(author_data)
    return author


@router.get("/authors/{author_id}/", response_model=PostAuthor)
async def get_author(
    author_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Получить автора"""
    crud = get_posts_crud(db)
    author = await crud.get_author(author_id)
    
    if not author:
        raise HTTPException(status_code=404, detail="Автор не найден")
    
    return author


# === ТЕГИ (Административные) ===

@router.post("/tags/", response_model=PostTag)
async def create_tag(
    tag_data: PostTagCreate,
    db: AsyncSession = Depends(get_db)
):
    """Создать тег"""
    crud = get_posts_crud(db)
    tag = await crud.create_tag(tag_data)
    return tag


# === МЕДИА ===

@router.post("/{post_id}/media/", response_model=PostMedia)
async def create_post_media(
    post_id: int,
    media_data: PostMediaCreate,
    db: AsyncSession = Depends(get_db)
):
    """Добавить медиа к посту"""
    crud = get_posts_crud(db)
    
    # Проверяем существование поста
    post = await crud.get_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")
    
    media_data.post_id = post_id
    media = await crud.create_media(media_data)
    return media


@router.get("/{post_id}/media/", response_model=List[PostMedia])
async def get_post_media(
    post_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Получить медиа поста"""
    crud = get_posts_crud(db)
    media = await crud.get_post_media(post_id)
    return media