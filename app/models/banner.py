# app/models/banner.py

from sqlalchemy import Column, Integer, String
from app.core.database import Base

class Banner(Base):
    __tablename__ = "banners"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    image = Column(String(255), nullable=False)
    url = Column(String(255), nullable=True)