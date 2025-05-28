from pydantic import BaseModel, HttpUrl

class BannerBase(BaseModel):
    title: str
    image: str
    url: HttpUrl | None = None

class BannerCreate(BannerBase):
    pass  # Используется, если когда-либо понадобится создавать через API

class Banner(BannerBase):
    id: int

    class Config:
        from_attributes = True