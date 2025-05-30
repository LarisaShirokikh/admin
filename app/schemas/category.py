# app/schemas/category.py
from pydantic import BaseModel, Field, field_validator, validator
from typing import Optional, List
from datetime import datetime

class CategoryBase(BaseModel):
    """Базовая схема категории"""
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    is_active: bool = True
    product_count: int = 0
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class CategoryCreate(BaseModel):
    """Схема для создания категории"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    is_active: bool = True
    image_url: Optional[str] = None
    meta_title: Optional[str] = Field(None, max_length=255)
    meta_description: Optional[str] = Field(None, max_length=500)
    meta_keywords: Optional[str] = Field(None, max_length=255)

    @field_validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Название категории не может быть пустым')
        return v.strip()

class CategoryUpdate(BaseModel):
    """Схема для обновления категории"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    is_active: Optional[bool] = None
    image_url: Optional[str] = None
    meta_title: Optional[str] = Field(None, max_length=255)
    meta_description: Optional[str] = Field(None, max_length=500)
    meta_keywords: Optional[str] = Field(None, max_length=255)

    @field_validator('name')
    def validate_name(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('Название категории не может быть пустым')
        return v.strip() if v else v

class CategoryList(BaseModel):
    """Схема для списка категорий с пагинацией"""
    items: List[CategoryBase]
    total: int
    page: int
    per_page: int
    pages: int

class CategorySearchParams(BaseModel):
    """Параметры поиска категорий"""
    query: Optional[str] = None
    is_active: Optional[bool] = None
    page: int = Field(1, ge=1)
    per_page: int = Field(10, ge=1, le=100)

class CategoryDeleteResponse(BaseModel):
    """Ответ при удалении категории"""
    message: str
    products_affected: int
    products_deleted: int
    products_unlinked: int

class CategoryStatusToggleResponse(BaseModel):
    """Ответ при изменении статуса категории"""
    message: str
    category: CategoryBase