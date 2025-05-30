# app/models/video.py
import uuid
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, ForeignKey, Text, func
from sqlalchemy.orm import relationship
from app.core.database import Base

class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String, unique=True, default=lambda: str(uuid.uuid4()), index=True)
    title = Column(String, index=True)
    description = Column(Text, nullable=True)
    url = Column(String, nullable=False)
    thumbnail_url = Column(String, nullable=True)
    duration = Column(Float, nullable=True)  # в секундах
    
    # Только product_id, убираем product_slug
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_active = Column(Boolean, default=True)
    is_featured = Column(Boolean, default=False)
    
    # Связь с продуктом
    product = relationship("Product", back_populates="videos")