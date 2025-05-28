from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ImportLogBase(BaseModel):
    filename: str
    rows: int
    status: str = "in_progress"
    message: Optional[str] = None


class ImportLogCreate(ImportLogBase):
    pass


class ImportLogRead(ImportLogBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True  # orm_mode = True для Pydantic v2