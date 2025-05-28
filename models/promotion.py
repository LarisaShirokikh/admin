# app/models/promotion.py

from sqlalchemy import Column, Integer, String, Text
from app.core.database import Base

class Promotion(Base):
    __tablename__ = "promotions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    image = Column(String(255), nullable=True)
    url = Column(String, nullable=False)