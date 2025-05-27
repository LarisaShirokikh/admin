# app/schemas/brand.py
from typing import Optional
from pydantic import BaseModel

class BrandBase(BaseModel):
    name: str
    description: Optional[str] = None
    logo_url: Optional[str] = None
    website: Optional[str] = None
    is_active: bool = True

class BrandCreate(BrandBase):
    slug: Optional[str] = None

class BrandUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    website: Optional[str] = None
    is_active: Optional[bool] = None

class Brand(BrandBase):
    id: int
    slug: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        orm_mode = True