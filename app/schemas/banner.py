# app/schemas/banner.py
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, field_validator


class BannerResponse(BaseModel):
    id: int
    image_url: str
    title: Optional[str] = None
    subtitle: Optional[str] = None
    href: Optional[str] = None
    badge: Optional[str] = None
    text_color: str = "light"
    show_button: bool = True
    sort_order: int = 0

    @field_validator('show_button', mode='before')
    @classmethod
    def coerce_show_button(cls, v):
        return True if v is None else v

    class Config:
        from_attributes = True


class BannerListResponse(BaseModel):
    items: List[BannerResponse]
    total: int


class BannerAdminResponse(BannerResponse):
    is_active: bool = True
    expires_at: Optional[datetime] = None
    is_archived: bool = False   # ← вычисляемое на бэке
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class BannerAdminListResponse(BaseModel):
    items: List[BannerAdminResponse]
    total: int


class BannerUpdate(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    href: Optional[str] = None
    badge: Optional[str] = None
    text_color: Optional[str] = None
    show_button: Optional[bool] = None
    expires_at: Optional[datetime] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

class BannerReorderItem(BaseModel):
    id: int
    sort_order: int


class BannerReorderRequest(BaseModel):
    items: List[BannerReorderItem]