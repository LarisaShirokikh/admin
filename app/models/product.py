# Унифицированная модель Product
import uuid
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
from .attributes import product_categories

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)  # Добавлено в админку
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, unique=True, index=True)  # Добавлено в админку
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False, default=0)
    discount_price = Column(Float, nullable=True)  # Добавлено в админку
    brand_id = Column(Integer, ForeignKey('brands.id', ondelete='SET NULL'), nullable=True)  # Добавлено в админку
    catalog_id = Column(Integer, ForeignKey("catalogs.id"), nullable=False)  # Оставлено из админки
    in_stock = Column(Boolean, default=True)
    characteristics = Column(JSON, nullable=True)  # Согласуется с attributes
    
    # Дополнительные поля из бэкенда
    type = Column(String(100), nullable=True, index=True)  # Добавлено в админку
    is_active = Column(Boolean, default=True)  # Добавлено в админку
    is_new = Column(Boolean, default=False)  # Добавлено в админку
    popularity_score = Column(Float, default=0)  # Добавлено в админку
    rating = Column(Float, default=0)  # Добавлено в админку
    review_count = Column(Integer, default=0)  # Добавлено в админку
    attributes = Column(JSON, default=dict)  
    meta_title = Column(String(255), nullable=True)  # Добавлено в админку
    meta_description = Column(String(500), nullable=True)  # Добавлено в админку
    meta_keywords = Column(String(255), nullable=True)  # Добавлено в админку
    created_at = Column(DateTime(timezone=True), server_default=func.now())  # Добавлено в админку
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())  # Добавлено в админку

    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)

    # Связи
    catalog = relationship("Catalog", back_populates="products")
    categories = relationship("Category", secondary=product_categories, back_populates="products")
    brand = relationship("Brand", back_populates="products")  # Добавлено в админку
    reviews = relationship("Review", back_populates="product", cascade="all, delete-orphan")  # Добавлено в админку
    product_images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan")
    product_video_items = relationship("ProductVideo", back_populates="product")
    videos = relationship("Video", back_populates="product", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Product {self.name}>"