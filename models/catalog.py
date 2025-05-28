# Модель Catalog с полями из обоих приложений
from sqlalchemy import Boolean, Column, DateTime, Integer, String, ForeignKey, Text, func
from sqlalchemy.orm import relationship
from app.core.database import Base

class Catalog(Base):
    __tablename__ = "catalogs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, unique=True, index=True)  # Добавлено в админку
    description = Column(Text, nullable=True)  # Добавлено в админку
    image = Column(String(255), nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=True)
    is_active = Column(Boolean, default=True)  # Добавлено в админку
    created_at = Column(DateTime(timezone=True), server_default=func.now())  # Добавлено в админку
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())  # Добавлено в админку

    # Связи
    category = relationship("Category", backref="catalogs")
    products = relationship("Product", back_populates="catalog")
    brand = relationship("Brand", back_populates="catalogs")

    catalog_images = relationship("CatalogImage", back_populates="catalog", cascade="all, delete-orphan")
    def __repr__(self):
        return f"<Catalog {self.name}>"