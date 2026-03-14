# app/models/banner.py

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.core.database import Base


class Banner(Base):
    __tablename__ = "banners"

    id = Column(Integer, primary_key=True, index=True)
    image_url = Column(String(500), nullable=False)
    title = Column(String(255), nullable=True)
    subtitle = Column(String(500), nullable=True)
    href = Column(String(500), nullable=True)
    badge = Column(String(50), nullable=True)
    text_color = Column(String(10), default="light")
    show_button = Column(Boolean, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    sort_order = Column(Integer, default=0, index=True)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Banner {self.id}: {self.title or self.image_url}>"