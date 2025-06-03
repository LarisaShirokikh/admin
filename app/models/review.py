from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    author_name = Column(String(255), nullable=False)
    author_email = Column(String(255), nullable=True)
    rating = Column(Float, nullable=False, default=5.0)
    title = Column(String(255), nullable=True)
    comment = Column(Text, nullable=True)
    is_approved = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Связь с продуктом
    product = relationship("Product", back_populates="reviews")

    def __repr__(self):
        return f"<Review {self.author_name} - {self.rating}>"