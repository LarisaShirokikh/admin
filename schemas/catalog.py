# app/schemas/catalog.py (обновленная версия)
from typing import Optional
from pydantic import BaseModel

class CatalogBase(BaseModel):
    name: str
    category_id: int
    description: Optional[str] = None
    image: Optional[str] = None
    is_active: bool = True
    category_id: Optional[int] = None  # Делаем опциональным, т.к. теперь есть brand_id
    brand_id: Optional[int] = None 

class CatalogCreate(CatalogBase):
    slug: Optional[str] = None


class CatalogUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    category_id: Optional[int] = None
    description: Optional[str] = None
    image: Optional[str] = None  # Добавлено поле для фото
    is_active: Optional[bool] = None

class Catalog(CatalogBase):
    id: int
    slug: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        orm_mode = True