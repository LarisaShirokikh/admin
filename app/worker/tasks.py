import asyncio
import logging
import shutil
from typing import List, Optional, Type

import pandas as pd
from celery import shared_task

from app.core.celery_config import celery_app
from app.core.database import AsyncSessionLocal
from app.crud.import_log import create_import_log, update_import_log_status
from app.crud.scraper import unregister_task

logger = logging.getLogger(__name__)


# === Event loop helper ===

def _get_loop() -> asyncio.AbstractEventLoop:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def _cleanup_loop():
    asyncio.set_event_loop(None)


# === Common scraper runner ===

def _run_scrape_task(
    self,
    scraper_class: Type,
    catalog_urls: List[str],
    username: str,
    scraper_name: str,
):
    """Common logic for all scraper Celery tasks."""
    logger.info("%s: starting %d URLs for %s", scraper_name, len(catalog_urls), username)
    loop = _get_loop()

    try:
        async def process():
            async with AsyncSessionLocal() as db:
                try:
                    scraper = scraper_class()
                    total = await scraper.parse_multiple_catalogs(catalog_urls, db)
                    return total
                except Exception as e:
                    await db.rollback()
                    raise

        total_products = loop.run_until_complete(process())
        logger.info("%s: completed, %d products", scraper_name, total_products)

        return {
            "status": "success",
            "processed": total_products,
            "message": f"{scraper_name} completed, {total_products} products",
        }

    except Exception as e:
        logger.error("%s failed: %s", scraper_name, e, exc_info=True)

        self.update_state(
            state="FAILURE",
            meta={"progress": 0, "error": str(e), "message": f"{scraper_name} failed: {e}"},
        )

        if self.request.retries >= self.max_retries:
            raise
        countdown = 30 * (2 ** self.request.retries)
        self.retry(exc=e, countdown=countdown)

    finally:
        try:
            unregister_task(username, self.request.id)
        except Exception as err:
            logger.error("Failed to unregister task %s: %s", self.request.id, err)
        _cleanup_loop()


# === Scraper tasks ===

@shared_task(bind=True, max_retries=3)
def scrape_labirint_multiple_catalogs_task(self, catalog_urls: List[str], username: str):
    from app.scrapers import LabirintScraper
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
    from app.scrapers import IntecronScraper
    return _run_scrape_task(self, IntecronScraper, catalog_urls, username, "Intecron")


@shared_task(bind=True, max_retries=3)
def scrape_as_doors_multiple_catalogs_task(self, catalog_urls: List[str], username: str):
    from app.scrapers import AsDoorsScraper
    return _run_scrape_task(self, AsDoorsScraper, catalog_urls, username, "AS-Doors")


# === CSV import tasks ===

@celery_app.task
def log_csv_import_task(filename: str, rows: int):
    logger.info("CSV import: %s, %d rows", filename, rows)
    return {"filename": filename, "rows": rows}


@celery_app.task
def import_csv_task(file_path: str):
    loop = _get_loop()

    async def run():
        async with AsyncSessionLocal() as db:
            log = await create_import_log(db, filename=file_path.split("/")[-1], rows=0)
            try:
                df = pd.read_csv(file_path)
                from app.services.csv_import import import_products_from_df
                await import_products_from_df(df, db)
                await update_import_log_status(db, log.id, status="success")
            except Exception as e:
                await update_import_log_status(db, log.id, status="failed", message=str(e))
                raise

    try:
        loop.run_until_complete(run())
    finally:
        _cleanup_loop()