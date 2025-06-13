import logging
import os
import traceback
from typing import List, Optional

from celery import shared_task
from sqlalchemy import func, select
from app.core.celery_config import celery_app
import pandas as pd
import asyncio
from app.core.database import AsyncSessionLocal
from app.crud.import_log import create_import_log, update_import_log_status

from app.models.category import Category
from app.scrapers.bunker_doors import BunkerDoorsScraper
from app.services.csv_import import import_products_from_df
from app.scrapers import AsDoorsScraper, LabirintScraper, IntecronScraper

# НОВЫЙ ИМПОРТ для снятия задач с учета
from app.crud.scraper import unregister_task_by_username

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger('celery_tasks')


@celery_app.task
def log_csv_import_task(filename: str, rows: int):
    print(f"[CSV IMPORT] Файл: {filename}, строк: {rows}")
    return {"filename": filename, "rows": rows}

@celery_app.task
def import_csv_task(file_path: str):
    loop = asyncio.get_event_loop()
    df = pd.read_csv(file_path)

    async def run():
        async with AsyncSessionLocal() as db:
            # создаём лог
            log = await create_import_log(db, filename=file_path.split("/")[-1], rows=len(df))

            try:
                # Импортируем продукты из CSV
                await import_products_from_df(df, db)
                
                
                await update_import_log_status(db, log.id, status="success")
            except Exception as e:
                await update_import_log_status(db, log.id, status="failed", message=str(e))
                raise e  # пробросим для дебага

    loop.run_until_complete(run())

@shared_task(bind=True, max_retries=3)
def scrape_labirint_multiple_catalogs_task(self, catalog_urls: List[str], username: str):
    """
    Celery задача для парсинга с динамической категоризацией
    """
    logger.info(f"Запуск задачи парсинга {len(catalog_urls)} каталогов Labirint для пользователя {username}")
    
    # Создаем новый event loop для каждого запуска задачи
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    try:
        # Определяем асинхронную функцию для обработки каталогов
        async def process_catalogs():
            async with AsyncSessionLocal() as db:
                try:
                    scraper = LabirintScraper()
                    
                    # Проверяем наличие активных категорий
                    result = await db.execute(
                        select(func.count(Category.id)).where(Category.is_active == True)
                    )
                    category_count = result.scalar_one()
                    
                    if category_count == 0:
                        raise Exception("В базе данных нет активных категорий!")
                    
                    # Проверяем наличие категории "Все двери"
                    result = await db.execute(
                        select(func.count(Category.id)).where(
                            func.lower(Category.name).like('%все двери%'),
                            Category.is_active == True
                        )
                    )
                    default_category_count = result.scalar_one()
                    
                    if default_category_count == 0:
                        self.update_state(
                            state='WARNING',
                            meta={
                                'message': 'Не найдена категория "Все двери". Будет использована первая доступная категория.',
                                'categories_available': category_count
                            }
                        )
                    
                    # Запускаем парсинг
                    total_products = await scraper.parse_multiple_catalogs(catalog_urls, db)
                    
                    self.update_state(
                        state='SUCCESS',
                        meta={
                            'total_products': total_products,
                            'categories_used': category_count,
                            'message': f'Обработано {total_products} продуктов и распределено по {category_count} категориям'
                        }
                    )
                    
                    return total_products
                    
                except Exception as e:
                    await db.rollback()
                    logger.error(f"Ошибка при парсинге каталогов Labirint: {e}", exc_info=True)
                    raise e
        
        # Выполняем асинхронную функцию в event loop
        total_products = loop.run_until_complete(process_catalogs())
        
        logger.info(f"Задача парсинга Labirint завершена успешно: {total_products} товаров")
        
        return {
            'status': 'success',
            'processed': total_products,
            'message': f"Парсинг Labirint завершен, обработано {total_products} товаров"
        }
        
    except Exception as e:
        logger.error(f"Ошибка при парсинге Labirint: {e}", exc_info=True)
        
        # Повторяем задачу с экспоненциальной задержкой
        countdown = 30 * (2 ** self.request.retries)  # 30 сек, 60 сек, 120 сек
        
        self.update_state(
            state="FAILURE",
            meta={
                'progress': 0,
                'error': str(e),
                'message': f"Ошибка при парсинге Labirint: {str(e)}"
            }
        )
        
        # НЕ делаем retry, если это последняя попытка - чтобы задача завершилась
        if self.request.retries >= self.max_retries:
            raise e
        else:
            self.retry(exc=e, countdown=countdown)
        
        return {
            'status': 'error',
            'error': str(e),
            'message': "Парсинг Labirint завершился с ошибкой"
        }
    finally:
        # КРИТИЧЕСКИ ВАЖНО: Автоматически снимаем задачу с учета при завершении
        try:
            unregister_task_by_username(username, self.request.id)
            logger.info(f"Task {self.request.id} automatically unregistered for user {username}")
        except Exception as cleanup_error:
            logger.error(f"Failed to unregister task {self.request.id}: {cleanup_error}")
        
        # Очищаем текущий event loop, но не закрываем его
        if 'loop' in locals() and loop.is_running():
            loop.stop()
        # Удаляем ссылку на event loop из текущего потока
        asyncio.set_event_loop(None)

@shared_task(bind=True, max_retries=3)
def scrape_intecron_multiple_catalogs_task(self, catalog_urls: Optional[List[str]] = None, username: str = "unknown"):
    """
    Задача Celery для парсинга нескольких каталогов Intecron с автокатегоризацией.
    """
    # Проверяем, что URL указаны и не пустые
    if not catalog_urls:
        logger.error("!!! Celery: список URL каталогов пуст !!!")
        # Снимаем задачу с учета даже при ошибке
        unregister_task_by_username(username, self.request.id)
        return False
        
    logger.info(f"!!! Celery: запуск задачи scrape_intecron_multiple_catalogs_task с {len(catalog_urls)} каталогами для пользователя {username} !!!")
    logger.info(f"!!! Celery: URL для парсинга: {catalog_urls} !!!")
    
    try:
        # Создаем новый event loop для каждого запуска задачи
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Определяем асинхронную функцию для обработки каталогов
            async def process_catalogs():
                async with AsyncSessionLocal() as db:
                    try:
                        # Создаем экземпляр скрапера и запускаем парсинг
                        scraper = IntecronScraper()
                        return await scraper.parse_multiple_catalogs(catalog_urls, db)
                    except Exception as e:
                        await db.rollback()
                        logger.error(f"Ошибка при парсинге каталогов: {e}", exc_info=True)
                        raise e
            
            # Выполняем асинхронную функцию в event loop
            total_products = loop.run_until_complete(process_catalogs())
            
            logger.info(f"!!! Celery: scrape_intecron_multiple_catalogs_task завершена успешно: {total_products} товаров !!!")
            return total_products
        finally:
            # Очищаем текущий event loop, но не закрываем его
            if 'loop' in locals() and loop.is_running():
                loop.stop()
            # Удаляем ссылку на event loop из текущего потока
            asyncio.set_event_loop(None)
    
    except Exception as exc:
        logger.error(f"!!! Celery: Ошибка при выполнении задачи: {exc} !!!")
        logger.error(traceback.format_exc())
        
        # НЕ делаем retry, если это последняя попытка
        if self.request.retries >= self.max_retries:
            raise exc
        else:
            # Повторяем задачу с экспоненциальной задержкой
            countdown = 30 * (2 ** self.request.retries)  # 30 сек, 60 сек, 120 сек
            self.retry(exc=exc, countdown=countdown)
        
        return False
    finally:
        # КРИТИЧЕСКИ ВАЖНО: Автоматически снимаем задачу с учета при завершении
        try:
            unregister_task_by_username(username, self.request.id)
            logger.info(f"Task {self.request.id} automatically unregistered for user {username}")
        except Exception as cleanup_error:
            logger.error(f"Failed to unregister task {self.request.id}: {cleanup_error}")
    
@shared_task(bind=True, max_retries=3)
def scrape_as_doors_multiple_catalogs_task(self, catalog_urls: List[str], username: str):
    """
    Celery задача для парсинга нескольких каталогов AS-Doors
    """
    logger.info(f"Запуск задачи парсинга {len(catalog_urls)} каталогов AS-Doors для пользователя {username}")
    
    # Создаем новый event loop для каждого запуска задачи
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    try:
        # Определяем асинхронную функцию для обработки каталогов
        async def process_catalogs():
            async with AsyncSessionLocal() as db:
                try:
                    # Создаем экземпляр скрапера и запускаем парсинг
                    scraper = AsDoorsScraper()
                    return await scraper.parse_multiple_catalogs(catalog_urls, db)
                except Exception as e:
                    await db.rollback()
                    logger.error(f"Ошибка при парсинге каталогов AS-Doors: {e}", exc_info=True)
                    raise e
        
        # Выполняем асинхронную функцию в event loop
        total_products = loop.run_until_complete(process_catalogs())
        
        # Обновляем статус
        self.update_state(
            state="SUCCESS",
            meta={
                'progress': 100,
                'message': f"Парсинг AS-Doors завершен, обработано {total_products} товаров"
            }
        )
        
        logger.info(f"Задача парсинга AS-Doors завершена успешно: {total_products} товаров")
        
        return {
            'status': 'success',
            'processed': total_products,
            'message': f"Парсинг AS-Doors завершен, обработано {total_products} товаров"
        }
        
    except Exception as e:
        logger.error(f"Ошибка при парсинге AS-Doors: {e}", exc_info=True)
        
        self.update_state(
            state="FAILURE",
            meta={
                'progress': 0,
                'message': f"Ошибка: {str(e)}"
            }
        )
        
        # НЕ делаем retry, если это последняя попытка
        if self.request.retries >= self.max_retries:
            raise e
        else:
            # Повторяем задачу с экспоненциальной задержкой
            countdown = 30 * (2 ** self.request.retries)  # 30 сек, 60 сек, 120 сек
            self.retry(exc=e, countdown=countdown)
        
        return {
            'status': 'error',
            'error': str(e),
            'message': "Парсинг AS-Doors завершился с ошибкой"
        }
    finally:
        # КРИТИЧЕСКИ ВАЖНО: Автоматически снимаем задачу с учета при завершении
        try:
            unregister_task_by_username(username, self.request.id)
            logger.info(f"Task {self.request.id} automatically unregistered for user {username}")
        except Exception as cleanup_error:
            logger.error(f"Failed to unregister task {self.request.id}: {cleanup_error}")
        
        # Очищаем текущий event loop, но не закрываем его
        if 'loop' in locals() and loop.is_running():
            loop.stop()
        # Удаляем ссылку на event loop из текущего потока
        asyncio.set_event_loop(None)


@shared_task(bind=True, max_retries=3)
def scrape_bunker_doors_multiple_catalogs_task(self, catalog_urls: List[str], username: str):
    """
    Celery задача для парсинга каталогов Bunker Doors
    """
    logger.info(f"Запуск задачи парсинга {len(catalog_urls)} каталогов Bunker Doors для пользователя {username}")
    
    # Создаем новый event loop для каждого запуска задачи
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    try:
        # Определяем асинхронную функцию для обработки каталогов
        async def process_catalogs():
            async with AsyncSessionLocal() as db:
                try:
                    # Обновляем статус задачи
                    self.update_state(
                        state='PROGRESS',
                        meta={
                            'progress': 10,
                            'message': 'Инициализация парсера Bunker Doors...',
                            'stage': 'initialization'
                        }
                    )
                    
                    # Создаем экземпляр скрапера и запускаем парсинг
                    scraper = BunkerDoorsScraper()
                    
                    # Проверяем/создаем бренд "Бункер"
                    brand_id = await scraper.ensure_brand_exists(db)
                    
                    self.update_state(
                        state='PROGRESS',
                        meta={
                            'progress': 20,
                            'message': f'Бренд "Бункер" готов (ID: {brand_id}). Начинаем парсинг...',
                            'stage': 'brand_ready'
                        }
                    )
                    
                    total_products = await scraper.parse_multiple_catalogs(catalog_urls, db)
                    
                    self.update_state(
                        state='SUCCESS',
                        meta={
                            'progress': 100,
                            'total_products': total_products,
                            'brand': 'Бункер',
                            'message': f'Парсинг Bunker Doors завершен, обработано {total_products} товаров'
                        }
                    )
                    
                    return total_products
                    
                except Exception as e:
                    await db.rollback()
                    logger.error(f"Ошибка при парсинге каталогов Bunker Doors: {e}", exc_info=True)
                    raise e
        
        # Выполняем асинхронную функцию в event loop
        total_products = loop.run_until_complete(process_catalogs())
        
        logger.info(f"Задача парсинга Bunker Doors завершена успешно: {total_products} товаров")
        
        return {
            'status': 'success',
            'processed': total_products,
            'brand': 'Бункер',
            'message': f"Парсинг Bunker Doors завершен, обработано {total_products} товаров"
        }
        
    except Exception as e:
        logger.error(f"Ошибка при парсинге Bunker Doors: {e}", exc_info=True)
        
        self.update_state(
            state="FAILURE",
            meta={
                'progress': 0,
                'error': str(e),
                'message': f"Ошибка при парсинге Bunker Doors: {str(e)}"
            }
        )
        
        # НЕ делаем retry, если это последняя попытка
        if self.request.retries >= self.max_retries:
            raise e
        else:
            # Повторяем задачу с экспоненциальной задержкой
            countdown = 30 * (2 ** self.request.retries)  # 30 сек, 60 сек, 120 сек
            self.retry(exc=e, countdown=countdown)
        
        return {
            'status': 'error',
            'error': str(e),
            'message': "Парсинг Bunker Doors завершился с ошибкой"
        }
    finally:
        # КРИТИЧЕСКИ ВАЖНО: Автоматически снимаем задачу с учета при завершении
        try:
            unregister_task_by_username(username, self.request.id)
            logger.info(f"Task {self.request.id} automatically unregistered for user {username}")
        except Exception as cleanup_error:
            logger.error(f"Failed to unregister task {self.request.id}: {cleanup_error}")
        
        # Очищаем текущий event loop, но не закрываем его
        if 'loop' in locals() and loop.is_running():
            loop.stop()
        # Удаляем ссылку на event loop из текущего потока
        asyncio.set_event_loop(None)