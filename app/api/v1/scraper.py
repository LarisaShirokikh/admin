# app/api/endpoints/scraper.py
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from typing import List, Optional
from app.core.database import AsyncSessionLocal
from app.worker.tasks import (
    scrape_bunker_doors_multiple_catalogs_task,
    scrape_intecron_multiple_catalogs_task, 
    scrape_labirint_multiple_catalogs_task, 
    scrape_as_doors_multiple_catalogs_task
)
router = APIRouter()

class ScraperRequest(BaseModel):
    """Запрос на парсинг каталогов"""
    catalog_urls: List[str]
    
class ScraperResponse(BaseModel):
    """Ответ на запрос парсинга"""
    task_id: str
    message: str

class ScraperStatus(BaseModel):
    """Статус задачи парсинга"""
    task_id: str
    status: str
    progress: Optional[float] = None
    result: Optional[dict] = None
    error: Optional[str] = None

@router.post("/scrape-labirint", response_model=ScraperResponse)
async def scrape_catalogs(request: ScraperRequest):
    """
    Запускает задачу парсинга нескольких каталогов Лабиринт.
    
    """
    if not request.catalog_urls:
        raise HTTPException(status_code=400, detail="Необходимо указать хотя бы один URL каталога")
    
    # Запускаем задачу Celery
    task = scrape_labirint_multiple_catalogs_task.delay(request.catalog_urls)
    
    return ScraperResponse(
        task_id=task.id,
        message=f"Задача парсинга {len(request.catalog_urls)} каталогов запущена успешно"
    )

@router.post("/scrape-bunker-doors", response_model=ScraperResponse)
async def scrape_bunker_doors_catalogs(request: ScraperRequest):
    """
    Запускает задачу парсинга нескольких каталогов Bunker Doors.
    
    Логика работы:
    - Все продукты автоматически получают бренд "Bunker Doors"
    - Все продукты обязательно помещаются в категорию "Все двери"
    - Дополнительно продукты распределяются по подходящим категориям из БД
    - Категории общие для всех брендов
    """
    if not request.catalog_urls:
        raise HTTPException(status_code=400, detail="Необходимо указать хотя бы один URL каталога")
    
    # Запускаем задачу Celery
    task = scrape_bunker_doors_multiple_catalogs_task.delay(request.catalog_urls)
    
    return ScraperResponse(
        task_id=task.id,
        message=f"Задача парсинга {len(request.catalog_urls)} каталогов Bunker Doors запущена. "
               f"Все продукты будут помещены в 'Все двери' + автоматически распределены по подходящим категориям."
    )


@router.post("/scrape-intecron", response_model=ScraperResponse)
async def scrape_intecron_catalogs(request: ScraperRequest):
    """
    Запускает задачу парсинга нескольких каталогов Интекрон.
    
    Args:
        request: Данные запроса с URL каталогов
    
    Returns:
        ID задачи Celery и сообщение
    """
    if not request.catalog_urls:
        raise HTTPException(status_code=400, detail="Необходимо указать хотя бы один URL каталога")
    
    # Нормализуем URL каталогов
    normalized_urls = []
    base_url = "https://intecron-msk.ru"
    
    for url in request.catalog_urls:
        # Удаляем ведущие и конечные пробелы
        url = url.strip()
        # Проверяем и нормализуем URL
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
    
    # Запускаем задачу Celery
    task = scrape_intecron_multiple_catalogs_task.delay(normalized_urls)
    
    return ScraperResponse(
        task_id=task.id,
        message=f"Задача парсинга {len(normalized_urls)} каталогов Интекрон запущена успешно"
    )

@router.post("/scrape-as-doors", response_model=ScraperResponse)
async def scrape_as_doors_catalogs(request: ScraperRequest):
    """
    Запускает задачу парсинга нескольких каталогов AS-Doors.
    
    Args:
        request: Данные запроса с URL каталогов
    
    Returns:
        ID задачи Celery и сообщение
    """
    if not request.catalog_urls:
        raise HTTPException(status_code=400, detail="Необходимо указать хотя бы один URL каталога")
    
    # Нормализуем URL каталогов
    normalized_urls = []
    for url in request.catalog_urls:
        # Удаляем ведущие и конечные пробелы
        url = url.strip()
        # Проверяем и нормализуем URL
        if url:
            if not url.startswith("http"):
                url = f"https://as-doors.ru{url}" if url.startswith('/') else f"https://as-doors.ru/{url}"
            normalized_urls.append(url)
    
    if not normalized_urls:
        raise HTTPException(status_code=400, detail="После нормализации не осталось валидных URL")
    
    # Запускаем задачу Celery
    task = scrape_as_doors_multiple_catalogs_task.delay(normalized_urls)
    
    return ScraperResponse(
        task_id=task.id,
        message=f"Задача парсинга {len(normalized_urls)} каталогов AS-Doors запущена успешно"
    )

@router.get("/scraper-status/{task_id}", response_model=ScraperStatus)
async def get_scraper_status(task_id: str):
    """
    Проверяет статус задачи парсинга.
    
    Args:
        task_id: ID задачи Celery
        
    Returns:
        Статус задачи и детали
    """
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
            else:
                response.status = "FAILURE"
                response.error = str(task_result.result)
                
        return response
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при получении статуса задачи: {str(e)}"
        )