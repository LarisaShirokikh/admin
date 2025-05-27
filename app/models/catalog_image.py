# Модель CatalogImage 
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base

class CatalogImage(Base):
    __tablename__ = "catalog_images"

    id = Column(Integer, primary_key=True, index=True)
    catalog_id = Column(Integer, ForeignKey("catalogs.id", ondelete="CASCADE"), nullable=False)
    url = Column(String, nullable=False)
    is_main = Column(Boolean, default=False)

    catalog = relationship("Catalog", back_populates="catalog_images")