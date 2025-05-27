# app/schemas/review.py
from typing import Optional
from pydantic import BaseModel, Field

class ReviewBase(BaseModel):
    product_id: int
    author_name: str
    rating: float = Field(..., ge=0, le=5)
    text: Optional[str] = None
    is_approved: int = 0

class ReviewCreate(ReviewBase):
    pass

class ReviewUpdate(BaseModel):
    author_name: Optional[str] = None
    rating: Optional[float] = Field(None, ge=0, le=5)
    text: Optional[str] = None
    is_approved: Optional[int] = None

class Review(ReviewBase):
    id: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        orm_mode = True