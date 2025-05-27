# app/models/product_ranking.py (в админ-бэкенде)
from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey, Float, Boolean, DateTime, JSON, String
from sqlalchemy.sql import func
from app.core.database import Base

class ProductRanking(Base):
    """Таблица для хранения данных о ранжировании продуктов"""
    __tablename__ = "product_rankings"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    # Базовые показатели для ранжирования
    ranking_score = Column(Float, default=0)  # Общий скор для ранжирования (0-100)
    
    # Административные настройки
    admin_score = Column(Float, default=0)  # Вручную установленный приоритет (0-100)
    is_featured = Column(Boolean, default=False)  # Выделенный товар
    priority_until = Column(DateTime(timezone=True), nullable=True)  # Приоритет до указанной даты
    
    # Сезонность и категориальные факторы
    seasonal_relevance = Column(JSON, nullable=True)  # {"winter": 80, "spring": 30, "summer": 10, "autumn": 40}
    category_boost = Column(Float, default=0)  # Множитель для категории товара
    
    # Метаданные для отслеживания качества товара
    impressions_count = Column(Integer, default=0)  # Количество показов (обновляется вручную или через GA)
    
    # Служебные поля
    last_recalculated = Column(DateTime(timezone=True), default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Дополнительно можно добавить другие специфические поля для ранжирования
    product_type_multiplier = Column(Float, default=1.0)  # Множитель для типа товара
    stock_status_multiplier = Column(Float, default=1.0)  # Множитель для статуса наличия
    price_range_multiplier = Column(Float, default=1.0)  # Множитель для ценового диапазона
    custom_tags = Column(JSON, nullable=True)  # Пользовательские теги для доп. фильтрации