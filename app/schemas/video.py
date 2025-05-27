# app/schemas/video.py
from pydantic import BaseModel, Field
from typing import Optional, List
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

class VideoCreate(VideoBase):
    pass

class VideoUpdate(BaseModel):
    id: int
    uuid: str
    title: str
    description: Optional[str] = None
    url: str
    thumbnail_url: Optional[str] = None
    duration: Optional[float] = None
    detection_confidence: Optional[float] = None
    
    # Оставляем только поля для продукта
    product_slug: Optional[str] = None
    product_id: Optional[int] = None
    
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_active: bool = True
    is_featured: bool = False
    auto_detected: Optional[bool] = False

    class Config:
        orm_mode = True

class VideoInDB(VideoBase):
    id: int
    uuid: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True

class Video(VideoInDB):
    pass
