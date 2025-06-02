# app/schemas/brand.py
from pydantic import BaseModel, HttpUrl, field_validator, model_validator, Field, ConfigDict
from typing import Optional, Any, Dict
from datetime import datetime

class BrandBase(BaseModel):
    """Базовая схема бренда"""
    name: str = Field(..., min_length=1, max_length=100, description="Название бренда")
    slug: Optional[str] = Field(None, max_length=100, description="URL-slug бренда")
    description: Optional[str] = Field(None, description="Описание бренда")
    logo_url: Optional[HttpUrl] = Field(None, description="URL логотипа")
    website: Optional[HttpUrl] = Field(None, description="Веб-сайт бренда")
    is_active: bool = Field(True, description="Активен ли бренд")

class BrandCreate(BrandBase):
    """Схема для создания бренда"""
    
    @model_validator(mode='after')
    def generate_slug_if_empty(self) -> 'BrandCreate':
        """Автогенерация slug из имени, если не указан"""
        if not self.slug and self.name:
            import re
            slug = re.sub(r'[^a-zA-Z0-9\-]', '-', self.name.lower())
            slug = re.sub(r'-+', '-', slug).strip('-')
            self.slug = slug
        return self

class BrandUpdate(BaseModel):
    """Схема для обновления бренда (все поля опциональные)"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    slug: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    logo_url: Optional[HttpUrl] = None
    website: Optional[HttpUrl] = None
    is_active: Optional[bool] = None

class BrandResponse(BrandBase):
    """Схема для ответа с брендом"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

class BrandInDB(BrandResponse):
    """Схема бренда в базе данных"""
    pass

class BrandBrief(BaseModel):
    """Краткая информация о бренде для связанных объектов"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    name: str
    slug: Optional[str] = None
    logo_url: Optional[str] = None