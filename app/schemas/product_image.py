# app/schemas/product_image.py (если еще не создан)
from typing import Optional
from pydantic import BaseModel

class ProductImageBase(BaseModel):
    url: str
    is_main: bool = False

class ProductImageCreate(ProductImageBase):
    pass

class ProductImageUpdate(BaseModel):
    url: Optional[str] = None
    is_main: Optional[bool] = None

class ProductImage(ProductImageBase):
    id: int
    product_id: int

    class Config:
        orm_mode = True