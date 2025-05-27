
# app/schemas/product.py
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field
from app.schemas.product_image import ProductImageCreate, ProductImage
from app.schemas.color import Color
from app.schemas.material import Material
from app.schemas.brand import Brand
from app.schemas.review import Review

class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    discount_price: Optional[float] = None
    in_stock: bool = True
    characteristics: Optional[Dict[str, Any]] = None
    attributes: Optional[Dict[str, Any]] = None
    is_active: bool = True
    is_new: bool = False
    type: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None

class ProductCreate(ProductBase):
    images: List[ProductImageCreate] = []
    brand_id: Optional[int] = None
    catalog_id: int  # Добавляем обязательное поле catalog_id
    slug: Optional[str] = None  # Добавляем поле slug
    image: Optional[str] = None 

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    discount_price: Optional[float] = None
    in_stock: Optional[bool] = None
    characteristics: Optional[Dict[str, Any]] = None
    attributes: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    is_new: Optional[bool] = None
    type: Optional[str] = None
    brand_id: Optional[int] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None
    category_ids: Optional[List[int]] = None  # Список ID категорий
    primary_category_id: Optional[int] = None  # ID основной категории
    colors: Optional[List[int]] = None  # Список ID цветов
    materials: Optional[List[int]] = None  # Список ID материалов

class ProductListItem(BaseModel):
    id: int
    uuid: str
    name: str
    slug: str
    price: float
    discount_price: Optional[float] = None
    in_stock: bool
    is_active: bool
    is_new: bool
    rating: float = 0
    review_count: int = 0
    main_image: Optional[str] = None
    
    class Config:
        orm_mode = True

class ProductDetail(ProductBase):
    id: int
    uuid: str
    slug: str
    catalog_id: int
    brand_id: Optional[int] = None
    popularity_score: float = 0
    rating: float = 0
    review_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    images: List[ProductImage] = []
    brand: Optional[Brand] = None
    colors: List[Color] = []
    materials: List[Material] = []
    reviews: List[Review] = []
    categories: List[Dict[str, Any]] = []
    primary_category: Optional[Dict[str, Any]] = None

    class Config:
        orm_mode = True

class ProductFilter(BaseModel):
    category_id: Optional[int] = None
    catalog_id: Optional[int] = None
    brand_id: Optional[int] = None
    color_id: Optional[int] = None
    material_id: Optional[int] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    is_new: Optional[bool] = None
    in_stock: Optional[bool] = None
    search: Optional[str] = None
    sort_by: Optional[str] = "popularity"  # popularity, price_asc, price_desc, rating
    page: int = 1
    per_page: int = 20