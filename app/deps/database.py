# app/deps/database.py
from app.core.database import AsyncSessionLocal

async def get_db():
    """Получить сессию базы данных"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()