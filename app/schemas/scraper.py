from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class ScraperType(str, Enum):
    LABIRINT = "labirint"
    BUNKER = "bunker"
    INTECRON = "intecron"
    AS_DOORS = "as-doors"


class ScraperRequest(BaseModel):
    catalog_urls: List[str]


class ScraperResponse(BaseModel):
    task_id: str
    message: str
    initiated_by: str
    urls_count: int


class ScraperStatus(BaseModel):
    task_id: str
    status: str
    progress: Optional[float] = None
    result: Optional[dict] = None
    error: Optional[str] = None