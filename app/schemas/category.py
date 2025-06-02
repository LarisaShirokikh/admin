# app/schemas/category.py (под вашу модель)
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List
from datetime import datetime

class CategoryBase(BaseModel):
    """Базовая схема категории"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    image_url: Optional[str] = None
    is_active: bool = True
    meta_title: Optional[str] = Field(None, max_length=255)
    meta_description: Optional[str] = Field(None, max_length=500)
    meta_keywords: Optional[str] = Field(None, max_length=255)

class CategoryCreate(CategoryBase):
    """Схема для создания категории"""
    slug: Optional[str] = None
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Название категории не может быть пустым')
        return v.strip()

class CategoryUpdate(BaseModel):
    """Схема для обновления категории"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = None
    meta_title: Optional[str] = Field(None, max_length=255)
    meta_description: Optional[str] = Field(None, max_length=500)
    meta_keywords: Optional[str] = Field(None, max_length=255)

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('Название категории не может быть пустым')
        return v.strip() if v else v

class CategoryResponse(CategoryBase):
    """Схема для ответа с категорией"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    slug: str
    product_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

class CategoryBrief(BaseModel):
    """Краткая информация о категории для связанных объектов"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    name: str
    slug: str
    image_url: Optional[str] = None

# Остальные схемы для API
class CategoryList(BaseModel):
    """Схема для списка категорий с пагинацией"""
    items: List[CategoryResponse]
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
    category: CategoryResponse