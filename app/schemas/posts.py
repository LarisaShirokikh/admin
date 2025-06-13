# app/schemas/posts.py

from datetime import datetime
from typing import List, Optional, Any
from pydantic import BaseModel, Field, ConfigDict


# Базовые схемы для автора
class PostAuthorBase(BaseModel):
    name: str = Field(..., max_length=255)
    email: str = Field(..., max_length=255)
    avatar: Optional[str] = Field(None, max_length=500)
    role: Optional[str] = Field(None, max_length=100)
    bio: Optional[str] = None


class PostAuthorCreate(PostAuthorBase):
    pass


class PostAuthorUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    avatar: Optional[str] = Field(None, max_length=500)
    role: Optional[str] = Field(None, max_length=100)
    bio: Optional[str] = None
    is_active: Optional[bool] = None


class PostAuthor(PostAuthorBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


# Базовые схемы для тегов
class PostTagBase(BaseModel):
    name: str = Field(..., max_length=100)
    slug: str = Field(..., max_length=120)
    description: Optional[str] = None
    color: Optional[str] = Field(None, max_length=7, description="HEX цвет тега")


class PostTagCreate(PostTagBase):
    pass


class PostTagUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    slug: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = None
    color: Optional[str] = Field(None, max_length=7, description="HEX цвет тега")
    is_active: Optional[bool] = None


class PostTag(PostTagBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    posts_count: int = 0
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


# Базовые схемы для медиа
class PostMediaBase(BaseModel):
    type: str = Field(..., max_length=20)  # image, video
    url: str = Field(..., max_length=500)
    thumbnail: Optional[str] = Field(None, max_length=500)
    alt_text: Optional[str] = Field(None, max_length=255)
    caption: Optional[str] = None
    order: int = Field(default=0)
    is_featured: bool = Field(default=False)
    file_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None


class PostMediaCreate(PostMediaBase):
    post_id: int


class PostMediaUpdate(BaseModel):
    type: Optional[str] = Field(None, max_length=20)
    url: Optional[str] = Field(None, max_length=500)
    thumbnail: Optional[str] = Field(None, max_length=500)
    alt_text: Optional[str] = Field(None, max_length=255)
    caption: Optional[str] = None
    order: Optional[int] = None
    is_featured: Optional[bool] = None
    file_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None


class PostMedia(PostMediaBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    post_id: int
    created_at: datetime


# Базовые схемы для постов
class PostBase(BaseModel):
    title: str = Field(..., max_length=500)
    slug: str = Field(..., max_length=550)
    excerpt: Optional[str] = None
    content: str
    meta_title: Optional[str] = Field(None, max_length=500)
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = Field(None, max_length=500)
    status: str = Field(default="draft", max_length=20)
    is_published: bool = Field(default=False)
    is_featured: bool = Field(default=False)
    is_pinned: bool = Field(default=False)


class PostCreate(PostBase):
    author_id: int
    tag_ids: Optional[List[int]] = []
    published_at: Optional[datetime] = None
    extra_data: Optional[dict] = None


class PostUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    slug: Optional[str] = Field(None, max_length=550)
    excerpt: Optional[str] = None
    content: Optional[str] = None
    meta_title: Optional[str] = Field(None, max_length=500)
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = Field(None, max_length=500)
    status: Optional[str] = Field(None, max_length=20)
    is_published: Optional[bool] = None
    is_featured: Optional[bool] = None
    is_pinned: Optional[bool] = None
    author_id: Optional[int] = None
    tag_ids: Optional[List[int]] = None
    published_at: Optional[datetime] = None
    extra_data: Optional[dict] = None


class Post(PostBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    author_id: Optional[int] = None
    views_count: int = 0
    likes_count: int = 0
    shares_count: int = 0
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    extra_data: Optional[dict] = None
    
    # Связанные объекты
    author: Optional[PostAuthor] = None
    tags: List[PostTag] = []
    media: List[PostMedia] = []
    featured_media: Optional[PostMedia] = None


# Схемы для списков и пагинации
class PostListItem(BaseModel):
    """Упрощенная схема поста для списков"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    title: str
    slug: str
    excerpt: Optional[str] = None
    is_published: bool
    is_featured: bool
    is_pinned: bool
    views_count: int = 0
    likes_count: int = 0
    published_at: Optional[datetime] = None
    created_at: datetime
    
    # Связанные объекты (упрощенные)
    author: Optional[PostAuthor] = None
    tags: List[PostTag] = []
    featured_media: Optional[PostMedia] = None


class PostSearchParams(BaseModel):
    """Параметры поиска постов"""
    q: Optional[str] = None
    tag_id: Optional[int] = None
    tag_slug: Optional[str] = None
    author_id: Optional[int] = None
    status: Optional[str] = None
    is_published: Optional[bool] = None
    is_featured: Optional[bool] = None
    is_pinned: Optional[bool] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    order_by: Optional[str] = Field(default="created_at")
    order_dir: Optional[str] = Field(default="desc")


class PostListResponse(BaseModel):
    """Ответ со списком постов"""
    items: List[PostListItem]
    total: int
    page: int
    per_page: int
    pages: int


# Схемы для статистики
class PostViewCreate(BaseModel):
    post_id: int
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    referer: Optional[str] = None
    session_id: Optional[str] = None


class PostLikeCreate(BaseModel):
    post_id: int
    ip_address: Optional[str] = None
    session_id: Optional[str] = None


# Схемы для популярных тегов
class PopularTag(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    name: str
    slug: str
    color: Optional[str] = None
    posts_count: int
    