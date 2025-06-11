# app/schemas/product.py (правильные связи: 1 бренд, много категорий)
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

# Импортируем схемы связанных объектов
from app.schemas.brand import BrandResponse, BrandBrief
from app.schemas.catalog import CatalogBrief, CatalogResponse
from app.schemas.category import CategoryResponse
from app.schemas.product_image import ProductImageCreate, ProductImage
from app.schemas.review import Review

class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    discount_price: Optional[float] = None
    in_stock: bool = True
    type: Optional[str] = None
    is_active: bool = True
    is_new: bool = False
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None

class ProductCreate(ProductBase):
    slug: Optional[str] = None
    brand_id: Optional[int] = None  # Один бренд
    catalog_id: int  
    category_id: Optional[int] = None  # Основная категория (прямая связь)
    category_ids: Optional[List[int]] = []  # Дополнительные категории (many-to-many)
    images: List[ProductImageCreate] = []

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    discount_price: Optional[float] = None
    in_stock: Optional[bool] = None
    type: Optional[str] = None
    is_active: Optional[bool] = None
    is_new: Optional[bool] = None
    brand_id: Optional[int] = None  # Один бренд
    catalog_id: Optional[int] = None
    category_id: Optional[int] = None  # Основная категория
    category_ids: Optional[List[int]] = None  # Дополнительные категории
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None

class ProductListItem(BaseModel):
    """Продукт в списке с одним брендом и каталогом"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    uuid: str
    name: str
    slug: str
    price: float
    discount_price: Optional[float] = None
    in_stock: bool
    is_active: bool
    is_new: bool
    type: Optional[str] = None
    popularity_score: float = 0
    rating: float = 0
    review_count: int = 0
    main_image: Optional[str] = None
    
    categories: List[CategoryResponse] = []
    brand: Optional[BrandBrief] = None
    catalog: Optional[CatalogBrief] = None

class ProductDetail(ProductBase):
    """Детальная информация о продукте: один бренд, много категорий"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    uuid: str
    slug: str
    brand_id: Optional[int] = None
    catalog_id: int
    category_id: Optional[int] = None  # Основная категория
    popularity_score: float = 0
    rating: float = 0
    review_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    main_image: Optional[str] = None
    
    # Связанные объекты
    brand: Optional[BrandResponse] = None  # ОДИН бренд
    catalog: Optional[CatalogResponse] = None  # ОДИН каталог
    categories: List[CategoryResponse] = []  # МНОГО категорий (many-to-many)
    images: List[ProductImage] = []
    reviews: List[Review] = []

class ProductFilter(BaseModel):
    category_id: Optional[int] = None
    catalog_id: Optional[int] = None
    brand_id: Optional[int] = None  # Фильтр по одному бренду
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    is_new: Optional[bool] = None
    in_stock: Optional[bool] = None
    search: Optional[str] = None
    sort_by: Optional[str] = Field(default="popularity_score", description="popularity_score, price, name, rating, created_at")
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)

# Дополнительные схемы
class ProductResponse(ProductDetail):
    """Алиас для ProductDetail"""
    pass

class ProductCreateResponse(ProductBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    uuid: str
    slug: str
    brand_id: Optional[int] = None
    catalog_id: int
    category_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    brand: Optional[BrandBrief] = None  # Один бренд
    catalog: Optional[CatalogBrief] = None  # Один каталог

class BatchUpdateError(BaseModel):
    product_id: int
    error: str

class BatchUpdateRequest(BaseModel):
    product_ids: List[int]
    update_data: ProductUpdate

class BatchUpdateResponse(BaseModel):
    success_count: int
    failed_count: int
    updated_products: List[int]
    failed_products: List[BatchUpdateError]

    class Config:
        from_attributes = True


class PriceUpdateRequest(BaseModel):
    scope: str = Field(..., description="Область применения: all, brand, category, catalog")
    scope_id: Optional[int] = Field(None, description="ID элемента для фильтрации")
    price_type: str = Field(..., description="Тип цены: main, discount, both")
    change_type: str = Field(..., description="Тип изменения: percent, fixed")
    change_value: float = Field(..., gt=0, description="Значение изменения")
    direction: str = Field(..., description="Направление: increase, decrease")
    only_active: Optional[bool] = Field(True, description="Только активные товары")
    only_in_stock: Optional[bool] = Field(False, description="Только товары в наличии")
    price_range: Optional[Dict[str, Optional[float]]] = Field(None, description="Диапазон цен")

class PriceUpdateResponse(BaseModel):
    success_count: int
    failed_count: int
    updated_products: List[int]
    failed_products: List[Dict[str, Any]]
    total_price_change: float

class ProductCountRequest(BaseModel):
    scope: str
    scope_id: Optional[int] = None
    only_active: Optional[bool] = True
    only_in_stock: Optional[bool] = False
    price_range: Optional[Dict[str, Optional[float]]] = None