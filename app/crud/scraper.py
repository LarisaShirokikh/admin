from collections import defaultdict
import logging

from fastapi import HTTPException
from sqlalchemy import func, select


from app.core.database import AsyncSessionLocal
from app.core.config import settings, active_scraping_tasks
from app.models.admin import AdminUser
from app.models.category import Category


logger = logging.getLogger("crud_product")



async def check_categories_exist() -> dict:
    """
    Проверяет наличие активных категорий в базе данных
    Возвращает информацию о состоянии категорий
    """
    async with AsyncSessionLocal() as session:
        try:
            # Считаем количество активных категорий
            result = await session.execute(
                select(func.count(Category.id)).where(Category.is_active == True)
            )
            active_count = result.scalar() or 0
            
            # Считаем общее количество категорий
            result = await session.execute(
                select(func.count(Category.id))
            )
            total_count = result.scalar() or 0
            
            return {
                "active_categories": active_count,
                "total_categories": total_count,
                "has_categories": active_count > 0
            }
            
        except Exception as e:
            print(f"ERROR: Failed to check categories: {str(e)}")
            return {
                "active_categories": 0,
                "total_categories": 0,
                "has_categories": False,
                "error": str(e)
            }

def check_scraping_limits(current_user: AdminUser) -> None:
    """Проверка лимитов на количество одновременных задач скрапинга"""
    user_tasks = active_scraping_tasks[current_user.username]
    total_tasks = sum(active_scraping_tasks.values())
    
    if user_tasks >= settings.MAX_CONCURRENT_TASKS_PER_USER:
        raise HTTPException(
            status_code=429,
            detail=f"Превышен лимит задач на пользователя ({settings.MAX_CONCURRENT_TASKS_PER_USER}). "
                   f"Дождитесь завершения текущих задач."
        )
    
    if total_tasks >= settings.MAX_CONCURRENT_TASKS_GLOBAL:
        raise HTTPException(
            status_code=429,
            detail=f"Превышен глобальный лимит задач ({settings.MAX_CONCURRENT_TASKS_GLOBAL}). "
                   f"Попробуйте позже."
        )

def register_task(current_user: AdminUser, task_id: str) -> None:
    """Регистрация новой задачи"""
    active_scraping_tasks[current_user.username] += 1
    print(f"TASK_REGISTERED: {task_id} by {current_user.username}. "
          f"User tasks: {active_scraping_tasks[current_user.username]}, "
          f"Total: {sum(active_scraping_tasks.values())}")

def unregister_task(current_user: AdminUser, task_id: str) -> None:
    """Снятие задачи с учета"""
    if active_scraping_tasks[current_user.username] > 0:
        active_scraping_tasks[current_user.username] -= 1
    print(f"TASK_UNREGISTERED: {task_id} by {current_user.username}")