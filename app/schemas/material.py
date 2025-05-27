# app/schemas/material.py
from typing import Optional
from pydantic import BaseModel

class MaterialBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True

class MaterialCreate(MaterialBase):
    pass

class MaterialUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class Material(MaterialBase):
    id: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        orm_mode = True