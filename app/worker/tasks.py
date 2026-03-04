"""
Celery задачи:
  - Скрапинг каталогов (с автоматическим скачиванием картинок)
  - Миграция старых внешних картинок в локальное хранилище
"""

import asyncio
import logging
from typing import List, Optional, Type

from celery import shared_task

from app.core.celery_config import celery_app
from app.crud.scraper import unregister_task

logger = logging.getLogger(__name__)


# === Engine factory — свежий engine для каждой задачи ===

def _create_task_session():
    """Создаёт новый engine + session factory, привязанные к текущему event loop."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.core.config import settings

    task_engine = create_async_engine(
        settings.database_url, future=True, echo=False
    )
    TaskSession = async_sessionmaker(task_engine, expire_on_commit=False)
    return task_engine, TaskSession


# === Common scraper runner ===

def _run_scrape_task(self, scraper_class: Type, catalog_urls: List[str], username: str, scraper_name: str):
    """Общая логика для всех Celery задач скрапинга."""
    logger.info("%s: запуск %d URL для %s", scraper_name, len(catalog_urls), username)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        async def process():
            task_engine, TaskSession = _create_task_session()
            try:
                async with TaskSession() as db:
                    scraper = scraper_class()
                    total = await scraper.sync_multiple_catalogs(catalog_urls, db)
                    return total
            finally:
                await task_engine.dispose()

        total_products = loop.run_until_complete(process())
        logger.info("%s: завершено, %d товаров", scraper_name, total_products)

        return {
            "status": "success",
            "processed": total_products,
            "message": f"{scraper_name}: обработано {total_products} товаров",
        }

    except Exception as e:
        logger.error("%s: ошибка: %s", scraper_name, e, exc_info=True)
        self.update_state(
            state="FAILURE",
            meta={"progress": 0, "error": str(e)},
        )
        if self.request.retries >= self.max_retries:
            raise
        self.retry(exc=e, countdown=30 * (2 ** self.request.retries))

    finally:
        try:
            unregister_task(username, self.request.id)
        except Exception as err:
            logger.error("Не удалось снять задачу %s: %s", self.request.id, err)
        loop.close()
        asyncio.set_event_loop(None)


# === Scraper tasks ===

@shared_task(bind=True, max_retries=3)
def scrape_labirint_multiple_catalogs_task(self, catalog_urls: List[str], username: str):
    from app.scrapers.labirint import LabirintScraper
    return _run_scrape_task(self, LabirintScraper, catalog_urls, username, "Labirint")


@shared_task(bind=True, max_retries=3)
def scrape_bunker_doors_multiple_catalogs_task(self, catalog_urls: List[str], username: str):
    from app.scrapers.bunker_doors import BunkerDoorsScraper
    return _run_scrape_task(self, BunkerDoorsScraper, catalog_urls, username, "Bunker Doors")


@shared_task(bind=True, max_retries=3)
def scrape_intecron_multiple_catalogs_task(self, catalog_urls: Optional[List[str]] = None, username: str = "unknown"):
    if not catalog_urls:
        unregister_task(username, self.request.id)
        return {"status": "error", "message": "No URLs provided"}
    from app.scrapers.intecron import IntecronScraper
    return _run_scrape_task(self, IntecronScraper, catalog_urls, username, "Intecron")


@shared_task(bind=True, max_retries=3)
def scrape_as_doors_multiple_catalogs_task(self, catalog_urls: List[str], username: str):
    from app.scrapers.as_doors import AsDoorsScraper
    return _run_scrape_task(self, AsDoorsScraper, catalog_urls, username, "AS-Doors")


# === Миграция изображений ===

@celery_app.task(bind=True)
def migrate_external_images_task(self, batch_size: int = 50):
    """
    Фоновая миграция: скачивает все внешние картинки и конвертирует в локальные WebP.
    Запускается через API: POST /admin/images/migrate
    """
    from app.models.product_image import ProductImage
    from app.services.image_service import ImageService
    from sqlalchemy import select, func

    logger.info("Запуск миграции внешних изображений (batch_size=%d)", batch_size)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        async def process():
            task_engine, TaskSession = _create_task_session()
            try:
                async with TaskSession() as db:
                    total_result = await db.execute(
                        select(func.count(ProductImage.id)).where(
                            ProductImage.is_local == False,
                            ProductImage.url.like("http%"),
                        )
                    )
                    total_external = total_result.scalar_one()
                    logger.info("Всего внешних изображений: %d", total_external)

                    migrated = 0
                    failed = 0
                    offset = 0

                    while True:
                        result = await db.execute(
                            select(ProductImage)
                            .where(
                                ProductImage.is_local == False,
                                ProductImage.url.like("http%"),
                            )
                            .order_by(ProductImage.id)
                            .offset(offset)
                            .limit(batch_size)
                        )
                        images = result.scalars().all()

                        if not images:
                            break

                        for img in images:
                            stored = ImageService.download_and_store(
                                url=img.url,
                                product_id=img.product_id,
                                image_index=img.id,
                                is_main=img.is_main,
                            )

                            if stored:
                                img.original_url = img.url
                                img.url = stored["local_url"]
                                img.is_local = True
                                img.file_size = stored["file_size"]
                                img.download_error = None
                                migrated += 1
                            else:
                                img.original_url = img.url
                                img.download_error = "Download or conversion failed"
                                failed += 1

                        await db.commit()
                        offset += batch_size

                        progress = min(100, int((migrated + failed) / max(total_external, 1) * 100))
                        self.update_state(
                            state="PROGRESS",
                            meta={
                                "progress": progress,
                                "migrated": migrated,
                                "failed": failed,
                                "total": total_external,
                            },
                        )
                        logger.info(
                            "Миграция: %d/%d скачано, %d ошибок",
                            migrated, total_external, failed,
                        )

                    return {
                        "migrated": migrated,
                        "failed": failed,
                        "total": total_external,
                    }
            finally:
                await task_engine.dispose()

        result = loop.run_until_complete(process())
        logger.info("Миграция завершена: %s", result)
        return {"status": "success", **result}

    except Exception as e:
        logger.error("Ошибка миграции: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}

    finally:
        loop.close()
        asyncio.set_event_loop(None)


# === CSV import tasks ===

@celery_app.task
def import_csv_task(file_path: str):
    import pandas as pd
    from app.crud.import_log import create_import_log, update_import_log_status

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        async def run():
            task_engine, TaskSession = _create_task_session()
            try:
                async with TaskSession() as db:
                    log = await create_import_log(db, filename=file_path.split("/")[-1], rows=0)
                    try:
                        df = pd.read_csv(file_path)
                        from app.services.csv_import import import_products_from_df
                        await import_products_from_df(df, db)
                        await update_import_log_status(db, log.id, status="success")
                    except Exception as e:
                        await update_import_log_status(db, log.id, status="failed", message=str(e))
                        raise
            finally:
                await task_engine.dispose()

        loop.run_until_complete(run())
    finally:
        loop.close()
        asyncio.set_event_loop(None)