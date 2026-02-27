# app/schemas/search.py
from typing import List, Optional, Union, Dict, Any
from pydantic import BaseModel

class SearchSuggestion(BaseModel):
    id: Union[int, str]
    name: str
    slug: str
    image: Optional[str] = None
    category: Optional[str] = None

class SearchSuggestionsResponse(BaseModel):
    suggestions: List[SearchSuggestion]

class SearchProductItem(BaseModel):
    id: int
    uuid: str
    name: str
    slug: str
    price: float
    discount_price: Optional[float] = None
    main_image: Optional[str] = None
    brand: Optional[Dict[str, Any]] = None
    categories: List[Dict[str, Any]] = []
    is_active: bool = True
    in_stock: bool = True
    created_at: Optional[str] = None

class SearchResponse(BaseModel):
    items: List[SearchProductItem]
    total: int
    page: int
    per_page: int
    pages: int