# app/crud/scraper.py

from collections import defaultdict
import logging

from fastapi import HTTPException
from sqlalchemy import func, select


from app.core.database import AsyncSessionLocal
from app.core.config import settings, active_scraping_tasks
from app.models.admin import AdminUser
from app.models.category import Category


logger = logging.getLogger("crud_scraper")



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

def sync_task_counters() -> dict:
    """
    Синхронизация счетчиков задач с реальным состоянием в Celery.
    Сбрасывает счетчики для завершенных задач.
    """
    try:
        # Получаем список всех активных задач из Celery
        from celery import current_app
        from celery.result import AsyncResult
        
        # Получаем инспектор Celery для проверки активных задач
        inspect = current_app.control.inspect()
        
        # Получаем активные задачи со всех воркеров
        active_tasks = inspect.active()
        
        if not active_tasks:
            # Если нет активных задач, сбрасываем все счетчики
            old_total = sum(active_scraping_tasks.values())
            active_scraping_tasks.clear()
            logger.info(f"SYNC: No active Celery tasks found, cleared {old_total} task counters")
            return {"cleared": old_total, "active_tasks": {}}
        
        # Собираем ID всех активных задач скрапинга
        scraper_task_names = [
            'app.worker.tasks.scrape_labirint_multiple_catalogs_task',
            'app.worker.tasks.scrape_intecron_multiple_catalogs_task',
            'app.worker.tasks.scrape_as_doors_multiple_catalogs_task',
            'app.worker.tasks.scrape_bunker_doors_multiple_catalogs_task'
        ]
        
        active_scraper_tasks = set()
        for worker_tasks in active_tasks.values():
            if worker_tasks:  # Проверяем что worker_tasks не None
                for task in worker_tasks:
                    if task.get('name') in scraper_task_names:
                        active_scraper_tasks.add(task['id'])
        
        # Если нет активных задач скрапинга, сбрасываем счетчики
        if not active_scraper_tasks:
            old_total = sum(active_scraping_tasks.values())
            active_scraping_tasks.clear()
            logger.info(f"SYNC: No active scraper tasks in Celery, cleared {old_total} counters")
            return {"cleared": old_total, "active_scraper_tasks": 0}
        
        # Если есть активные задачи, но их меньше чем в счетчиках - корректируем
        current_total = sum(active_scraping_tasks.values())
        real_total = len(active_scraper_tasks)
        
        if current_total > real_total:
            # Пропорционально уменьшаем счетчики
            ratio = real_total / current_total if current_total > 0 else 0
            for username in active_scraping_tasks:
                active_scraping_tasks[username] = max(0, int(active_scraping_tasks[username] * ratio))
            
            logger.info(f"SYNC: Adjusted task counters from {current_total} to {real_total}")
        
        return {
            "synced": True,
            "active_scraper_tasks": real_total,
            "current_counters": dict(active_scraping_tasks)
        }
        
    except Exception as e:
        logger.error(f"SYNC_ERROR: Failed to sync task counters: {e}")
        # В случае ошибки, консервативно не очищаем счетчики
        return {"error": str(e), "synced": False}

def check_scraping_limits(current_user: AdminUser) -> None:
    """Проверка лимитов на количество одновременных задач скрапинга"""
    # НОВАЯ ЛОГИКА: Сначала синхронизируем реальное состояние задач
    sync_task_counters()
    
    user_tasks = active_scraping_tasks[current_user.username]
    total_tasks = sum(active_scraping_tasks.values())
    
    logger.info(f"LIMIT_CHECK: User {current_user.username} has {user_tasks} tasks, total: {total_tasks}")
    
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

def unregister_task_by_username(username: str, task_id: str) -> None:
    """Снятие задачи с учета по имени пользователя (для использования в Celery задачах)"""
    if active_scraping_tasks[username] > 0:
        active_scraping_tasks[username] -= 1
    print(f"TASK_UNREGISTERED: {task_id} by {username}. "
          f"User tasks: {active_scraping_tasks[username]}, "
          f"Total: {sum(active_scraping_tasks.values())}")

def cleanup_dead_tasks() -> int:
    """
    Очистка "мертвых" задач. 
    Возвращает количество очищенных задач.
    """
    from celery.result import AsyncResult
    
    cleaned_count = 0
    
    # Проходим по всем активным задачам и проверяем их реальный статус
    for username, task_count in list(active_scraping_tasks.items()):
        if task_count > 0:
            # Здесь можно добавить логику проверки конкретных task_id, 
            # но для простоты просто сбрасываем счетчики, если система была перезагружена
            # В production нужно хранить task_id и проверять их статус
            pass
    
    logger.info(f"Cleaned up {cleaned_count} dead tasks")
    return cleaned_count

def sync_task_counters() -> dict:
    """
    Синхронизация счетчиков задач с реальным состоянием в Celery.
    Сбрасывает счетчики для завершенных задач.
    """
    try:
        # Получаем список всех активных задач из Celery
        from celery import current_app
        from celery.result import AsyncResult
        
        # Получаем инспектор Celery для проверки активных задач
        inspect = current_app.control.inspect()
        
        # Получаем активные задачи со всех воркеров
        active_tasks = inspect.active()
        
        if not active_tasks:
            # Если нет активных задач, сбрасываем все счетчики
            old_total = sum(active_scraping_tasks.values())
            active_scraping_tasks.clear()
            logger.info(f"SYNC: No active Celery tasks found, cleared {old_total} task counters")
            return {"cleared": old_total, "active_tasks": {}}
        
        # Собираем ID всех активных задач скрапинга
        scraper_task_names = [
            'app.worker.tasks.scrape_labirint_multiple_catalogs_task',
            'app.worker.tasks.scrape_intecron_multiple_catalogs_task',
            'app.worker.tasks.scrape_as_doors_multiple_catalogs_task',
            'app.worker.tasks.scrape_bunker_doors_multiple_catalogs_task'
        ]
        
        active_scraper_tasks = set()
        for worker_tasks in active_tasks.values():
            if worker_tasks:  # Проверяем что worker_tasks не None
                for task in worker_tasks:
                    if task.get('name') in scraper_task_names:
                        active_scraper_tasks.add(task['id'])
        
        # Если нет активных задач скрапинга, сбрасываем счетчики
        if not active_scraper_tasks:
            old_total = sum(active_scraping_tasks.values())
            active_scraping_tasks.clear()
            logger.info(f"SYNC: No active scraper tasks in Celery, cleared {old_total} counters")
            return {"cleared": old_total, "active_scraper_tasks": 0}
        
        # Если есть активные задачи, но их меньше чем в счетчиках - корректируем
        current_total = sum(active_scraping_tasks.values())
        real_total = len(active_scraper_tasks)
        
        if current_total > real_total:
            # Пропорционально уменьшаем счетчики
            ratio = real_total / current_total if current_total > 0 else 0
            for username in active_scraping_tasks:
                active_scraping_tasks[username] = max(0, int(active_scraping_tasks[username] * ratio))
            
            logger.info(f"SYNC: Adjusted task counters from {current_total} to {real_total}")
        
        return {
            "synced": True,
            "active_scraper_tasks": real_total,
            "current_counters": dict(active_scraping_tasks)
        }
        
    except Exception as e:
        logger.error(f"SYNC_ERROR: Failed to sync task counters: {e}")
        # В случае ошибки, консервативно не очищаем счетчики
        return {"error": str(e), "synced": False}

def force_cleanup_user_tasks(username: str) -> int:
    """Принудительная очистка всех задач пользователя"""
    old_count = active_scraping_tasks[username]
    active_scraping_tasks[username] = 0
    logger.info(f"Force cleaned {old_count} tasks for user {username}")
    return old_count