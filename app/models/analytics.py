# app/models/analytics.py
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Index
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from app.core.database import Base

class AnalyticsEvent(Base):
    """Таблица для хранения всех событий аналитики"""
    __tablename__ = "analytics_events"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, index=True, nullable=False)
    event_type = Column(String(50), index=True, nullable=False)  # view, interaction, etc.
    event_subtype = Column(String(50), index=True)  # view_image, contact_request, etc.
    
    # Данные события
    event_data = Column(JSON)  # duration_seconds, image_index, etc.
    
    # Данные сессии
    session_id = Column(String(100), index=True)
    user_agent = Column(Text)
    device_type = Column(String(20))
    referrer = Column(Text)
    page_url = Column(Text)
    ip_address = Column(String(45))
    
    # Временные метки
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Индексы для быстрого поиска
    __table_args__ = (
        Index('idx_product_event_date', 'product_id', 'event_type', 'created_at'),
        Index('idx_session_date', 'session_id', 'created_at'),
    )

class AnalyticsSession(Base):
    """Таблица для хранения сессий пользователей"""
    __tablename__ = "analytics_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), unique=True, index=True, nullable=False)
    
    # Информация о сессии
    user_agent = Column(Text)
    device_type = Column(String(20))
    ip_address = Column(String(45))
    
    # Данные сессии
    first_page = Column(Text)
    last_page = Column(Text)
    referrer = Column(Text)
    
    # Счетчики
    page_views = Column(Integer, default=0)
    products_viewed = Column(Integer, default=0)
    interactions_count = Column(Integer, default=0)
    
    # Временные метки
    started_at = Column(DateTime, default=datetime.utcnow, index=True)
    last_activity = Column(DateTime, default=datetime.utcnow, index=True)
    duration_seconds = Column(Integer, default=0)

class AnalyticsDailySummary(Base):
    """Агрегированная статистика по дням"""
    __tablename__ = "analytics_daily_summary"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, index=True, nullable=False)
    date = Column(DateTime, index=True, nullable=False)
    
    # Счетчики за день
    views_count = Column(Integer, default=0)
    detail_views_count = Column(Integer, default=0)
    interactions_count = Column(Integer, default=0)
    unique_sessions = Column(Integer, default=0)
    
    # Средние значения
    avg_view_duration = Column(Integer, default=0)  # в секундах
    total_view_duration = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_product_date', 'product_id', 'date'),
    )