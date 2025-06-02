# app/schemas/review.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime

class ReviewBase(BaseModel):
    """Базовая схема отзыва"""
    rating: int = Field(..., ge=1, le=5, description="Рейтинг от 1 до 5")
    comment: Optional[str] = Field(None, description="Текст отзыва")
    reviewer_name: Optional[str] = Field(None, description="Имя автора отзыва")
    reviewer_email: Optional[str] = Field(None, description="Email автора отзыва")
    is_verified: bool = Field(False, description="Подтвержден ли отзыв")
    is_active: bool = Field(True, description="Активен ли отзыв")

class ReviewCreate(ReviewBase):
    """Схема для создания отзыва"""
    product_id: int = Field(..., description="ID продукта")

class ReviewUpdate(BaseModel):
    """Схема для обновления отзыва"""
    rating: Optional[int] = Field(None, ge=1, le=5)
    comment: Optional[str] = None
    reviewer_name: Optional[str] = None
    reviewer_email: Optional[str] = None
    is_verified: Optional[bool] = None
    is_active: Optional[bool] = None

class Review(ReviewBase):
    """Схема отзыва"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    product_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

class ReviewResponse(Review):
    """Схема для ответа с отзывом"""
    pass

class ReviewBrief(BaseModel):
    """Краткая информация об отзыве"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    rating: int
    reviewer_name: Optional[str] = None
    created_at: datetime