# app/schemas/catalog_image.py (если еще не создан)
from typing import Optional
from pydantic import BaseModel

class CatalogImageBase(BaseModel):
    url: str
    is_main: bool = False

class CatalogImageCreate(CatalogImageBase):
    pass

class CatalogImageUpdate(BaseModel):
    url: Optional[str] = None
    is_main: Optional[bool] = None

class CatalogImage(CatalogImageBase):
    id: int
    catalog_id: int

    class Config:
        orm_mode = True