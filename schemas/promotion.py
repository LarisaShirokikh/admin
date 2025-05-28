from pydantic import BaseModel

class PromotionBase(BaseModel):
    title: str
    description: str | None = None
    image: str | None = None
    url: str | None = None

class PromotionCreate(PromotionBase):
    pass  # Используется, если когда-либо понадобится создавать через API

class Promotion(PromotionBase):
    id: int

    class Config:
        from_attributes = True