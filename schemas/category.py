# app/schemas/category.py (обновленная версия)
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

class CategoryBase(BaseModel):
    name: str
    manufacturer_id: int
    image_url: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None
    parent_id: Optional[int] = None

class CategoryCreate(CategoryBase):
    slug: Optional[str] = None

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    manufacturer_id: Optional[int] = None
    image_url: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None
    parent_id: Optional[int] = None

class Category(CategoryBase):
    id: int
    slug: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    product_count: Optional[int] = None  # Добавлено для отображения кол-ва продуктов

    class Config:
        orm_mode = True

class CategoryWithChildren(Category):
    children: List['CategoryWithChildren'] = []

    class Config:
        orm_mode = True

# Необходимо для корректной работы рекурсивной модели
CategoryWithChildren.model_rebuild()

