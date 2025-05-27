import asyncio
import logging
from app.core.database import AsyncSessionLocal
from app.crud.product import create_or_update_product, create_product
from app.scrapers.intecron import classify_and_update_product, ensure_brand_exists, get_category_map, parse_catalog_page, update_category_counters
from app.scrapers.labirint import parse_labirint_products

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger('scraper_runner')

async def run_labirint_scraper():
    logger.info("[SCRAPER] Старт скрейпинга (async)")

    catalog_url = "https://labirintdoors.ru/katalog/leolab"

    async with AsyncSessionLocal() as db:
        # Получаем продукты
        products = await parse_labirint_products(catalog_url, db)

        logger.info(f"[SCRAPER] Получено {len(products)} товаров для сохранения")

        saved_count = 0
        for p in products:
            try:
                # Здесь теперь вызов асинхронной функции с await
                await create_product(db, p)
                await db.commit()
                saved_count += 1
            except Exception as e:
                await db.rollback()
                logger.warning(f"[SCRAPER] Ошибка при сохранении товара: {e}")

        logger.info(f"[SCRAPER] Загружено {saved_count} товаров")
        return saved_count
    
async def run_intecron_scraper(catalog_url):
    """
    Запускает скрейпер для сайта Intecron
    """
    if not catalog_url:
        logger.error("[SCRAPER] Ошибка: URL каталога не указан")
        return 0
        
    logger.info("[SCRAPER] Старт скрейпинга Intecron (async)")
    logger.info(f"[SCRAPER] Используем URL каталога: {catalog_url}")

    async with AsyncSessionLocal() as db:
        try:
            # Получаем или создаем бренд Intecron
            brand_id = await ensure_brand_exists(db, "Intecron", "intecron")
            logger.info(f"[SCRAPER] Получен ID бренда Intecron: {brand_id}")
            
            # Используем новую функцию parse_catalog_page вместо parse_intecron_products
            products = await parse_catalog_page(catalog_url, db, brand_id)

            logger.info(f"[SCRAPER] Получено {len(products)} товаров для сохранения")

            saved_count = 0
            for p in products:
                try:
                    # Проверка, что бренд установлен
                    if not p.brand_id:
                        p.brand_id = brand_id
                        logger.info(f"[SCRAPER] Установлен бренд для товара: {p.name}")
                    
                    # Проверка, что изображения правильно ассоциированы
                    if p.images:
                        for img in p.images:
                            # Логируем для отладки
                            logger.info(f"[SCRAPER] Изображение для {p.name}: {img.url}, is_main={img.is_main}")
                    
                    # Создаем или обновляем продукт
                    created_product = await create_or_update_product(db, p)
                    if created_product:
                        saved_count += 1
                        logger.info(f"[SCRAPER] Сохранен товар: {p.name}")
                    
                    await db.commit()
                except Exception as e:
                    await db.rollback()
                    logger.warning(f"[SCRAPER] Ошибка при сохранении товара {p.name}: {e}")

            logger.info(f"[SCRAPER] Загружено {saved_count} товаров")
            return saved_count
        except Exception as e:
            logger.error(f"[SCRAPER] Ошибка при выполнении скрейпера: {e}", exc_info=True)
            await db.rollback()
            return 0