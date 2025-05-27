import logging
import os
import traceback
from typing import List, Optional

from celery import shared_task
from app.core.celery_config import celery_app
import pandas as pd
import asyncio
from app.core.database import AsyncSessionLocal
from app.crud.import_log import create_import_log, update_import_log_status

from app.services.csv_import import import_products_from_df
from app.scrapers import AsDoorsScraper, LabirintScraper, IntecronScraper

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

@celery_app.task(bind=True, max_retries=3)
def scrape_labirint_task(self):
    """Запуск скрейпера Labirint Doors с автоматической категоризацией"""
    logger.info("!!! Celery: запускаем scrape_labirint_task с категоризацией !!!")

    try:
        # Создаем или получаем event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        async def run_scraper():
            # Получаем список каталогов для парсинга
            # Здесь можно задать конкретные URL или получить их из базы данных
            catalog_urls = [
                'https://labirintdoors.ru/category/imperial',
                'https://labirintdoors.ru/category/grand',
                'https://labirintdoors.ru/category/piano',
                # Добавьте другие URL каталогов здесь
            ]
            
            async with AsyncSessionLocal() as db:
                # Создаем экземпляр скрапера и запускаем парсинг
                scraper = LabirintScraper()
                return await scraper.parse_multiple_catalogs(catalog_urls, db)
                
        result = loop.run_until_complete(run_scraper())
        logger.info("!!! Celery: scrape_labirint_task завершена успешно !!!")
        return result
    except Exception as e:
        logger.error(f"!!! Celery: ОШИБКА в scrape_labirint_task: {str(e)} !!!")
        traceback.print_exc()

        try:
            self.retry(exc=e, countdown=30)
        except Exception as retry_e:
            logger.error(f"!!! Celery: Ошибка при повторе задачи: {str(retry_e)} !!!")
            return False

@shared_task(bind=True, max_retries=3)
def scrape_labirint_multiple_catalogs_task(self, catalog_urls: List[str]):
    """
    Задача Celery для парсинга нескольких каталогов Лабиринт с автокатегоризацией.
    """
    logger.info(f"!!! Celery: запуск задачи scrape_labirint_multiple_catalogs_task с {len(catalog_urls)} каталогами !!!")
    
    try:
        # Гарантируем, что Event Loop отсутствует или создаем новый
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            # Запускаем асинхронный код в синхронном контексте Celery
            async def process_catalogs():
                async with AsyncSessionLocal() as db:
                    try:
                        # Создаем экземпляр скрапера и запускаем парсинг
                        scraper = LabirintScraper()
                        return await scraper.parse_multiple_catalogs(catalog_urls, db)
                    except Exception as e:
                        await db.rollback()
                        logger.error(f"Ошибка при парсинге каталогов: {e}", exc_info=True)
                        raise e
            
            # Выполняем асинхронную функцию в event loop
            total_products = loop.run_until_complete(process_catalogs())
            
            logger.info(f"!!! Celery: scrape_labirint_multiple_catalogs_task завершена успешно !!!")
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
        
        # Повторяем задачу с экспоненциальной задержкой
        countdown = 30 * (2 ** self.request.retries)  # 30 сек, 60 сек, 120 сек
        self.retry(exc=exc, countdown=countdown)
        
        return False

@celery_app.task(bind=True, max_retries=3)
def scrape_intecron_task(self):
    """Запуск скрейпера Intecron с автоматической категоризацией"""
    logger.info("!!! Celery: запускаем scrape_intecron_task с категоризацией !!!")

    try:
        # Создаем или получаем event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        async def run_scraper():
            # Получаем список каталогов для парсинга
            # Здесь можно задать конкретные URL или получить их из базы данных
            catalog_urls = [
                'https://intecron-msk.ru/catalog/doors/',
                'https://intecron-msk.ru/catalog/premium/',
                # Добавьте другие URL каталогов здесь
            ]
            
            async with AsyncSessionLocal() as db:
                # Создаем экземпляр скрапера и запускаем парсинг
                scraper = IntecronScraper()
                return await scraper.parse_multiple_catalogs(catalog_urls, db)
                
        result = loop.run_until_complete(run_scraper())
        logger.info("!!! Celery: scrape_intecron_task завершена успешно !!!")
        return result
    except Exception as e:
        logger.error(f"!!! Celery: ОШИБКА в scrape_intecron_task: {str(e)} !!!")
        traceback.print_exc()

        try:
            self.retry(exc=e, countdown=30)
        except Exception as retry_e:
            logger.error(f"!!! Celery: Ошибка при повторе задачи: {str(retry_e)} !!!")
            return False

@shared_task(bind=True, max_retries=3)
def scrape_intecron_multiple_catalogs_task(self, catalog_urls: Optional[List[str]] = None):
    """
    Задача Celery для парсинга нескольких каталогов Intecron с автокатегоризацией.
    """
    # Проверяем, что URL указаны и не пустые
    if not catalog_urls:
        logger.error("!!! Celery: список URL каталогов пуст !!!")
        return False
        
    logger.info(f"!!! Celery: запуск задачи scrape_intecron_multiple_catalogs_task с {len(catalog_urls)} каталогами !!!")
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
        
        # Повторяем задачу с экспоненциальной задержкой
        countdown = 30 * (2 ** self.request.retries)  # 30 сек, 60 сек, 120 сек
        self.retry(exc=exc, countdown=countdown)
        
        return False
    
@shared_task(bind=True, max_retries=3)
def scrape_as_doors_multiple_catalogs_task(self, catalog_urls: List[str]):
    """
    Celery задача для парсинга нескольких каталогов AS-Doors
    """
    logger.info(f"Запуск задачи парсинга {len(catalog_urls)} каталогов AS-Doors")
    
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
        
        # Повторяем задачу с экспоненциальной задержкой
        countdown = 30 * (2 ** self.request.retries)  # 30 сек, 60 сек, 120 сек
        
        self.update_state(
            state="FAILURE",
            meta={
                'progress': 0,
                'message': f"Ошибка: {str(e)}"
            }
        )
        
        self.retry(exc=e, countdown=countdown)
        
        return {
            'status': 'error',
            'error': str(e),
            'message': "Парсинг AS-Doors завершился с ошибкой"
        }
    finally:
        # Очищаем текущий event loop, но не закрываем его
        if 'loop' in locals() and loop.is_running():
            loop.stop()
        # Удаляем ссылку на event loop из текущего потока
        asyncio.set_event_loop(None)