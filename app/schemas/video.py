# app/schemas/video.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class VideoBase(BaseModel):
    title: str
    description: Optional[str] = None
    url: str
    thumbnail_url: Optional[str] = None
    duration: Optional[float] = None
    product_id: Optional[int] = None
    is_active: bool = True
    is_featured: bool = False

class VideoCreate(BaseModel):
    title: str
    description: Optional[str] = None
    url: str
    thumbnail_url: Optional[str] = None
    duration: Optional[float] = None
    product_id: Optional[int] = None
    is_active: bool = True
    is_featured: bool = False

class VideoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration: Optional[float] = None
    product_id: Optional[int] = None
    is_active: Optional[bool] = None
    is_featured: Optional[bool] = None

class VideoResponse(VideoBase):
    id: int
    uuid: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True