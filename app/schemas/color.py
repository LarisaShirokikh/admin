# app/schemas/color.py
from typing import Optional
from pydantic import BaseModel

class ColorBase(BaseModel):
    name: str
    code: Optional[str] = None
    is_active: bool = True

class ColorCreate(ColorBase):
    pass

class ColorUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    is_active: Optional[bool] = None

class Color(ColorBase):
    id: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        orm_mode = True