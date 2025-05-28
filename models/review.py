# app/models/review.py
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    author_name = Column(String(100), nullable=False)
    rating = Column(Float, nullable=False)
    text = Column(Text, nullable=True)
    is_approved = Column(Integer, default=0)  # 0 - на модерации, 1 - одобрен, -1 - отклонен
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Связь с продуктом
    product = relationship("Product", back_populates="reviews")

    def __repr__(self):
        return f"<Review #{self.id} для продукта {self.product_id}>"