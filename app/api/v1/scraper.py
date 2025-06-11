# app/api/endpoints/scraper.py (защищенная версия)
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, HttpUrl
from typing import List, Optional
from app.core.database import AsyncSessionLocal
from app.crud.scraper import check_categories_exist, check_scraping_limits, register_task, unregister_task
from app.worker.tasks import (
    scrape_bunker_doors_multiple_catalogs_task,
    scrape_intecron_multiple_catalogs_task, 
    scrape_labirint_multiple_catalogs_task, 
    scrape_as_doors_multiple_catalogs_task
)

# НОВЫЕ ИМПОРТЫ для защиты
from app.deps.admin_auth import get_current_active_admin, get_current_superuser, check_admin_rate_limit
from app.models.admin import AdminUser
from datetime import datetime, timedelta
from collections import defaultdict
from app.core.config import settings, active_scraping_tasks

router = APIRouter()


class ScraperRequest(BaseModel):
    """Запрос на парсинг каталогов"""
    catalog_urls: List[str]
    
class ScraperResponse(BaseModel):
    """Ответ на запрос парсинга"""
    task_id: str
    message: str
    initiated_by: str
    urls_count: int

class ScraperStatus(BaseModel):
    """Статус задачи парсинга"""
    task_id: str
    status: str
    progress: Optional[float] = None
    result: Optional[dict] = None
    error: Optional[str] = None




# ========== СКРАПИНГ ЛАБИРИНТ ==========

@router.post("/scrape-labirint", response_model=ScraperResponse)
async def scrape_catalogs(
    request: Request,
    scraper_request: ScraperRequest,
    current_user: AdminUser = Depends(get_current_active_admin)  # ЗАЩИТА
):
    """
    Запускает задачу парсинга нескольких каталогов Лабиринт.
    ТРЕБУЕТ: Права админа + строгий rate limiting
    """
    # КРИТИЧЕСКИ СТРОГИЙ rate limiting для скрапинга
    check_admin_rate_limit(request, max_requests=3, window_minutes=10)
    
    if not scraper_request.catalog_urls:
        raise HTTPException(status_code=400, detail="Необходимо указать хотя бы один URL каталога")
    
    # НОВАЯ ПРОВЕРКА: Проверяем наличие категорий ПЕРЕД запуском
    print(f"[SCRAPER] Checking categories before starting Labirint scraping...")
    categories_info = await check_categories_exist()
    
    if not categories_info["has_categories"]:
        error_detail = {
            "error_code": "NO_CATEGORIES",
            "message": "Для работы скрайпера необходимо создать активные категории товаров",
            "details": {
                "active_categories": categories_info["active_categories"],
                "total_categories": categories_info["total_categories"],
                "instructions": [
                    "Перейдите в раздел 'Категории' в админ-панели",
                    "Создайте как минимум одну категорию (например: 'Все двери')",
                    "Убедитесь что категория активна (галочка 'Активна')",
                    "Повторите запуск скрайпера"
                ],
                "suggested_categories": [
                    "Все двери",
                    "Входные двери", 
                    "Металлические двери",
                    "Межкомнатные двери"
                ]
            }
        }
        
        print(f"[SCRAPER] Categories check failed: {categories_info}")
        raise HTTPException(
            status_code=422,  # Unprocessable Entity - более подходящий код
            detail=error_detail
        )
    
    print(f"[SCRAPER] Categories check passed: {categories_info['active_categories']} active categories found")
    
    # Проверяем лимиты на одновременные задачи
    check_scraping_limits(current_user)
    
    # Валидация URLs
    valid_urls = [url.strip() for url in scraper_request.catalog_urls if url.strip()]
    if not valid_urls:
        raise HTTPException(status_code=400, detail="Не найдено валидных URL")
    
    if len(valid_urls) > 10:  # Ограничиваем количество URL в одной задаче
        raise HTTPException(
            status_code=400, 
            detail="Слишком много URL в одной задаче (максимум 10). Разбейте на несколько запросов."
        )
    
    try:
        # КРИТИЧЕСКОЕ ДЕЙСТВИЕ - подробное логирование
        print(f"CRITICAL_SCRAPING: Admin {current_user.username} starting Labirint scraping")
        print(f"URLs: {valid_urls}")
        print(f"Categories available: {categories_info['active_categories']}")
        
        # Запускаем задачу Celery
        task = scrape_labirint_multiple_catalogs_task.delay(valid_urls)
        
        # Регистрируем задачу
        register_task(current_user, task.id)
        
        print(f"SUCCESS: Labirint scraping task {task.id} started by {current_user.username}")
        
        return ScraperResponse(
            task_id=task.id,
            message=f"Задача парсинга {len(valid_urls)} каталогов Лабиринт запущена успешно. "
                   f"Найдено {categories_info['active_categories']} активных категорий.",
            initiated_by=current_user.username,
            urls_count=len(valid_urls)
        )
        
    except Exception as e:
        print(f"ERROR: Failed to start Labirint scraping by {current_user.username}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка запуска задачи: {str(e)}"
        )


# ========== СКРАПИНГ BUNKER DOORS ==========

@router.post("/scrape-bunker", response_model=ScraperResponse)
async def scrape_bunker_doors_catalogs(
    request: Request,
    scraper_request: ScraperRequest,
    current_user: AdminUser = Depends(get_current_active_admin)  # ЗАЩИТА
):
    """
    Запускает задачу парсинга нескольких каталогов Bunker Doors.
    ТРЕБУЕТ: Права админа + строгий rate limiting
    """
    # КРИТИЧЕСКИ СТРОГИЙ rate limiting
    check_admin_rate_limit(request, max_requests=300, window_minutes=10)
    
    if not scraper_request.catalog_urls:
        raise HTTPException(status_code=400, detail="Необходимо указать хотя бы один URL каталога")
    
    print(f"[SCRAPER] Checking categories before starting Bunker scraping...")
    categories_info = await check_categories_exist()

    print(f"[SCRAPER] Checking categories before starting Bunker scraping...")
    categories_info = await check_categories_exist()
    
    if not categories_info["has_categories"]:
        error_detail = {
            "error_code": "NO_CATEGORIES",
            "message": "Для работы скрайпера необходимо создать активные категории товаров",
            "details": {
                "active_categories": categories_info["active_categories"],
                "total_categories": categories_info["total_categories"],
                "instructions": [
                    "Перейдите в раздел 'Категории' в админ-панели",
                    "Создайте как минимум одну категорию (например: 'Все двери')",
                    "Убедитесь что категория активна (галочка 'Активна')",
                    "Повторите запуск скрайпера"
                ],
                "suggested_categories": [
                    "Все двери",
                    "Входные двери", 
                    "Металлические двери"
                ]
            }
        }
        
        print(f"[SCRAPER] Categories check failed: {categories_info}")
        raise HTTPException(
            status_code=422,  # Unprocessable Entity - более подходящий код
            detail=error_detail
        )
    
    print(f"[SCRAPER] Categories check passed: {categories_info['active_categories']} active categories found")
    
    # Проверяем лимиты на одновременные задачи
    check_scraping_limits(current_user)
    
    # Валидация URL каталогов
    valid_urls = []
    for url in scraper_request.catalog_urls:
        url = url.strip()
        if url:
            # Нормализуем URL для Bunker Doors
            if not url.startswith('http'):
                if not url.startswith('/'):
                    url = f"/{url}"
                url = f"https://bunkerdoors.ru{url}"
            valid_urls.append(url)
    
    if not valid_urls:
        raise HTTPException(status_code=400, detail="После нормализации не осталось валидных URL")
    
    if len(valid_urls) > 10:
        raise HTTPException(
            status_code=400, 
            detail="Слишком много URL в одной задаче (максимум 10)"
        )
    
    try:
        # КРИТИЧЕСКОЕ ДЕЙСТВИЕ - подробное логирование
        print(f"CRITICAL_SCRAPING: Admin {current_user.username} starting Bunker Doors scraping")
        print(f"URLs: {valid_urls}")
        
        # Запускаем задачу Celery
        task = scrape_bunker_doors_multiple_catalogs_task.delay(valid_urls)
        
        # Регистрируем задачу
        register_task(current_user, task.id)
        
        print(f"SUCCESS: Bunker Doors scraping task {task.id} started by {current_user.username}")
        
        return ScraperResponse(
            task_id=task.id,
            message=f"Задача парсинга {len(valid_urls)} каталогов бренда 'Бункер' запущена. "
                   f"Все продукты будут помещены в 'Все двери' + автоматически распределены по подходящим категориям.",
            initiated_by=current_user.username,
            urls_count=len(valid_urls)
        )
        
    except Exception as e:
        print(f"ERROR: Failed to start Bunker Doors scraping by {current_user.username}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка запуска задачи: {str(e)}"
        )

# ========== СКРАПИНГ ИНТЕКРОН ==========

@router.post("/scrape-intecron", response_model=ScraperResponse)
async def scrape_intecron_catalogs(
    request: Request,
    scraper_request: ScraperRequest,
    current_user: AdminUser = Depends(get_current_active_admin)  # ЗАЩИТА
):
    """
    Запускает задачу парсинга нескольких каталогов Интекрон.
    ТРЕБУЕТ: Права админа + строгий rate limiting
    """
    # КРИТИЧЕСКИ СТРОГИЙ rate limiting
    check_admin_rate_limit(request, max_requests=3, window_minutes=10)
    
    if not scraper_request.catalog_urls:
        raise HTTPException(status_code=400, detail="Необходимо указать хотя бы один URL каталога")
    
    # НОВАЯ ПРОВЕРКА: Проверяем наличие категорий ПЕРЕД запуском
    print(f"[SCRAPER] Checking categories before starting Labirint scraping...")
    categories_info = await check_categories_exist()
    
    if not categories_info["has_categories"]:
        error_detail = {
            "error_code": "NO_CATEGORIES",
            "message": "Для работы скрайпера необходимо создать активные категории товаров",
            "details": {
                "active_categories": categories_info["active_categories"],
                "total_categories": categories_info["total_categories"],
                "instructions": [
                    "Перейдите в раздел 'Категории' в админ-панели",
                    "Создайте как минимум одну категорию (например: 'Все двери')",
                    "Убедитесь что категория активна (галочка 'Активна')",
                    "Повторите запуск скрайпера"
                ],
                "suggested_categories": [
                    "Все двери",
                    "Входные двери", 
                    "Металлические двери",
                    "Межкомнатные двери"
                ]
            }
        }
        
        print(f"[SCRAPER] Categories check failed: {categories_info}")
        raise HTTPException(
            status_code=422,  # Unprocessable Entity - более подходящий код
            detail=error_detail
        )
    
    print(f"[SCRAPER] Categories check passed: {categories_info['active_categories']} active categories found")
    

    # Проверяем лимиты на одновременные задачи
    check_scraping_limits(current_user)
    
    # Нормализуем URL каталогов
    normalized_urls = []
    base_url = "https://intecron-msk.ru"
    
    for url in scraper_request.catalog_urls:
        url = url.strip()
        if url:
            if not url.startswith("http"):
                if not url.startswith('/'):
                    if '/' not in url:
                        url = f"/catalog/intekron/{url}/"
                    else:
                        url = f"/{url}"
                url = f"{base_url}{url}"
            normalized_urls.append(url)
    
    if not normalized_urls:
        raise HTTPException(status_code=400, detail="После нормализации не осталось валидных URL")
    
    if len(normalized_urls) > 10:
        raise HTTPException(
            status_code=400, 
            detail="Слишком много URL в одной задаче (максимум 10)"
        )
    
    try:
        # КРИТИЧЕСКОЕ ДЕЙСТВИЕ - подробное логирование
        print(f"CRITICAL_SCRAPING: Admin {current_user.username} starting Intecron scraping")
        print(f"URLs: {normalized_urls}")
        
        # Запускаем задачу Celery
        task = scrape_intecron_multiple_catalogs_task.delay(normalized_urls)
        
        # Регистрируем задачу
        register_task(current_user, task.id)
        
        print(f"SUCCESS: Intecron scraping task {task.id} started by {current_user.username}")
        
        return ScraperResponse(
            task_id=task.id,
            message=f"Задача парсинга {len(normalized_urls)} каталогов Интекрон запущена успешно",
            initiated_by=current_user.username,
            urls_count=len(normalized_urls)
        )
        
    except Exception as e:
        print(f"ERROR: Failed to start Intecron scraping by {current_user.username}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка запуска задачи: {str(e)}"
        )

# ========== СКРАПИНГ AS-DOORS ==========

@router.post("/scrape-as-doors", response_model=ScraperResponse)
async def scrape_as_doors_catalogs(
    request: Request,
    scraper_request: ScraperRequest,
    current_user: AdminUser = Depends(get_current_active_admin)  # ЗАЩИТА
):
    """
    Запускает задачу парсинга нескольких каталогов AS-Doors.
    ТРЕБУЕТ: Права админа + строгий rate limiting
    """
    # КРИТИЧЕСКИ СТРОГИЙ rate limiting
    check_admin_rate_limit(request, max_requests=3, window_minutes=10)
    
    if not scraper_request.catalog_urls:
        raise HTTPException(status_code=400, detail="Необходимо указать хотя бы один URL каталога")
    
    # НОВАЯ ПРОВЕРКА: Проверяем наличие категорий ПЕРЕД запуском
    print(f"[SCRAPER] Checking categories before starting Labirint scraping...")
    categories_info = await check_categories_exist()
    
    if not categories_info["has_categories"]:
        error_detail = {
            "error_code": "NO_CATEGORIES",
            "message": "Для работы скрайпера необходимо создать активные категории товаров",
            "details": {
                "active_categories": categories_info["active_categories"],
                "total_categories": categories_info["total_categories"],
                "instructions": [
                    "Перейдите в раздел 'Категории' в админ-панели",
                    "Создайте как минимум одну категорию (например: 'Все двери')",
                    "Убедитесь что категория активна (галочка 'Активна')",
                    "Повторите запуск скрайпера"
                ],
                "suggested_categories": [
                    "Все двери",
                    "Входные двери", 
                    "Металлические двери",
                    "Межкомнатные двери"
                ]
            }
        }
        
        print(f"[SCRAPER] Categories check failed: {categories_info}")
        raise HTTPException(
            status_code=422,  # Unprocessable Entity - более подходящий код
            detail=error_detail
        )
    
    print(f"[SCRAPER] Categories check passed: {categories_info['active_categories']} active categories found")
    

    # Проверяем лимиты на одновременные задачи
    check_scraping_limits(current_user)
    
    # Нормализуем URL каталогов
    normalized_urls = []
    for url in scraper_request.catalog_urls:
        url = url.strip()
        if url:
            if not url.startswith("http"):
                url = f"https://as-doors.ru{url}" if url.startswith('/') else f"https://as-doors.ru/{url}"
            normalized_urls.append(url)
    
    if not normalized_urls:
        raise HTTPException(status_code=400, detail="После нормализации не осталось валидных URL")
    
    if len(normalized_urls) > 10:
        raise HTTPException(
            status_code=400, 
            detail="Слишком много URL в одной задаче (максимум 10)"
        )
    
    try:
        # КРИТИЧЕСКОЕ ДЕЙСТВИЕ - подробное логирование
        print(f"CRITICAL_SCRAPING: Admin {current_user.username} starting AS-Doors scraping")
        print(f"URLs: {normalized_urls}")
        
        # Запускаем задачу Celery
        task = scrape_as_doors_multiple_catalogs_task.delay(normalized_urls)
        
        # Регистрируем задачу
        register_task(current_user, task.id)
        
        print(f"SUCCESS: AS-Doors scraping task {task.id} started by {current_user.username}")
        
        return ScraperResponse(
            task_id=task.id,
            message=f"Задача парсинга {len(normalized_urls)} каталогов AS-Doors запущена успешно",
            initiated_by=current_user.username,
            urls_count=len(normalized_urls)
        )
        
    except Exception as e:
        print(f"ERROR: Failed to start AS-Doors scraping by {current_user.username}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка запуска задачи: {str(e)}"
        )

# ========== МОНИТОРИНГ ЗАДАЧ ==========

@router.get("/scraper-status/{task_id}", response_model=ScraperStatus)
async def get_scraper_status(
    request: Request,
    task_id: str,
    current_user: AdminUser = Depends(get_current_active_admin)  # ЗАЩИТА
):
    """
    Проверяет статус задачи парсинга.
    """
    check_admin_rate_limit(request, max_requests=30, window_minutes=1)  # Мониторинг можно чаще
    
    # Импортируем здесь, чтобы избежать циклических импортов
    from celery.result import AsyncResult
    
    try:
        task_result = AsyncResult(task_id)
        
        response = ScraperStatus(
            task_id=task_id,
            status=task_result.status
        )
        
        # Добавляем прогресс, если доступен
        if hasattr(task_result, 'info') and isinstance(task_result.info, dict) and 'progress' in task_result.info:
            response.progress = task_result.info['progress']
            
        # Добавляем результат или ошибку
        if task_result.ready():
            if task_result.successful():
                response.result = task_result.result
                response.status = "SUCCESS"
                # Снимаем задачу с учета при завершении
                unregister_task(current_user, task_id)
            else:
                response.status = "FAILURE"
                response.error = str(task_result.result)
                # Снимаем задачу с учета при ошибке
                unregister_task(current_user, task_id)
                
        return response
        
    except Exception as e:
        print(f"ERROR: Failed to get task status {task_id} for {current_user.username}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при получении статуса задачи: {str(e)}"
        )

@router.get("/active-tasks")
async def get_active_tasks(
    request: Request,
    current_user: AdminUser = Depends(get_current_superuser)  # ТОЛЬКО СУПЕРАДМИН
):
    """
    Получить информацию об активных задачах скрапинга (только для суперадмина)
    """
    # check_admin_rate_limit(request, max_requests=10, window_minutes=1)
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Доступ запрещен. Только суперадмин может просматривать активные задачи.")
    total_tasks = sum(active_scraping_tasks.values())
    
    return {
        "total_active_tasks": total_tasks,
        "max_global_limit": settings.MAX_CONCURRENT_TASKS_GLOBAL,
        "max_user_limit": settings.MAX_CONCURRENT_TASKS_PER_USER,
        "tasks_by_user": dict(active_scraping_tasks),
        "requested_by": current_user.username,
        "timestamp": datetime.utcnow()
    }

@router.post("/cancel-all-tasks")
async def cancel_all_tasks(
    request: Request,
    current_user: AdminUser = Depends(get_current_superuser)  # ТОЛЬКО СУПЕРАДМИН
):
    """
    ЭКСТРЕННАЯ ОСТАНОВКА всех задач скрапинга (только суперадмин)
    """
    # check_admin_rate_limit(request, max_requests=5, window_minutes=5)
    
    # КРИТИЧЕСКОЕ ДЕЙСТВИЕ
    print(f"EMERGENCY: Superuser {current_user.username} cancelling ALL scraping tasks")
    
    # Очищаем счетчики
    cancelled_tasks = sum(active_scraping_tasks.values())
    active_scraping_tasks.clear()
    
    print(f"SUCCESS: {cancelled_tasks} tasks cancelled by superuser {current_user.username}")
    
    return {
        "message": f"Все задачи скрапинга отменены",
        "cancelled_tasks": cancelled_tasks,
        "cancelled_by": current_user.username,
        "timestamp": datetime.utcnow()
    }

@router.get("/check-readiness")
async def check_scraper_readiness(
    request: Request,
    current_user: AdminUser = Depends(get_current_active_admin)
):
    """
    Проверяет готовность системы к запуску скрайперов
    """
    # check_admin_rate_limit(request, max_requests=10, window_minutes=1)
    
    categories_info = await check_categories_exist()
    user_tasks = active_scraping_tasks[current_user.username]
    total_tasks = sum(active_scraping_tasks.values())
    
    readiness = {
        "ready": categories_info["has_categories"] and user_tasks < settings.MAX_CONCURRENT_TASKS_PER_USER,
        "categories": categories_info,
        "limits": {
            "user_tasks": user_tasks,
            "max_user_tasks": settings.MAX_CONCURRENT_TASKS_PER_USER,
            "total_tasks": total_tasks,
            "max_total_tasks": settings.MAX_CONCURRENT_TASKS_GLOBAL,
            "can_start_task": user_tasks < settings.MAX_CONCURRENT_TASKS_PER_USER and total_tasks < settings.MAX_CONCURRENT_TASKS_GLOBAL
        },
        "issues": []
    }
    
    # Добавляем список проблем
    if not categories_info["has_categories"]:
        readiness["issues"].append({
            "type": "no_categories",
            "message": "Нет активных категорий товаров",
            "action": "Создайте категории в разделе 'Категории'"
        })
    
    if user_tasks >= settings.MAX_CONCURRENT_TASKS_PER_USER:
        readiness["issues"].append({
            "type": "user_limit",
            "message": f"Превышен лимит задач на пользователя ({user_tasks}/{settings.MAX_CONCURRENT_TASKS_PER_USER})",
            "action": "Дождитесь завершения текущих задач"
        })
    
    if total_tasks >= settings.MAX_CONCURRENT_TASKS_GLOBAL:
        readiness["issues"].append({
            "type": "global_limit", 
            "message": f"Превышен глобальный лимит задач ({total_tasks}/{settings.MAX_CONCURRENT_TASKS_GLOBAL})",
            "action": "Попробуйте позже"
        })
    
    return readiness