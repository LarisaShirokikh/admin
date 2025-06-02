# app/schemas/catalog.py (под вашу модель)
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime

class CatalogBase(BaseModel):
    """Базовая схема каталога"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    image: Optional[str] = None
    is_active: bool = True

class CatalogCreate(CatalogBase):
    """Схема для создания каталога"""
    slug: Optional[str] = None
    category_id: Optional[int] = None
    brand_id: Optional[int] = None

class CatalogUpdate(BaseModel):
    """Схема для обновления каталога"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    is_active: Optional[bool] = None
    category_id: Optional[int] = None
    brand_id: Optional[int] = None

class CatalogResponse(CatalogBase):
    """Схема для ответа с каталогом"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    slug: str
    category_id: Optional[int] = None
    brand_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class CatalogBrief(BaseModel):
    """Краткая информация о каталоге для связанных объектов"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    name: str
    slug: str
    image: Optional[str] = None

# Алиас для обратной совместимости
Catalog = CatalogResponse