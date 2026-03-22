import logging
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.product import Product
from celery.result import AsyncResult



logger = logging.getLogger(__name__)


async def get_seo_stats(db: AsyncSession) -> dict:
    total = (await db.execute(
        select(func.count(Product.id)).where(Product.is_active == True)
    )).scalar() or 0

    with_seo = (await db.execute(
        select(func.count(Product.id)).where(
            Product.is_active == True,
            Product.description.isnot(None),
            Product.description != "",
        )
    )).scalar() or 0

    with_attrs = (await db.execute(
        select(func.count(Product.id)).where(
            Product.is_active == True,
            Product.attributes.isnot(None),
        )
    )).scalar() or 0

    return {
        "total_active": total,
        "with_seo_description": with_seo,
        "without_seo_description": total - with_seo,
        "with_attributes": with_attrs,
        "coverage_percent": round(with_seo / total * 100, 1) if total else 0,
    }


async def start_seo_bulk_generation(db: AsyncSession, only_empty: bool, username: str) -> dict:
    from app.core.config import settings
    if not settings.ANTHROPIC_ENABLED:
        return {"status": "error", "message": "Anthropic provider отключён (ANTHROPIC_ENABLED=false)"}

    query = select(func.count(Product.id)).where(
        Product.is_active == True,
        Product.attributes.isnot(None),
    )
    if only_empty:
        query = query.where(
            (Product.description == None) | (Product.description == "")
        )
    total = (await db.execute(query)).scalar() or 0

    if total == 0:
        return {"status": "ok", "message": "Нет товаров для обработки", "queued": 0}

    from app.worker.tasks import generate_seo_bulk_task
    task = generate_seo_bulk_task.delay(only_empty=only_empty)

    logger.info("SEO bulk task запущен пользователем %s, task_id=%s", username, task.id)

    return {
        "status": "started",
        "task_id": task.id,
        "estimated_products": total,
        "message": f"Задача запущена. Будет обработано ~{total} товаров.",
        "initiated_by": username,
    }


def get_seo_task_status(task_id: str) -> dict:
    result = AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": result.status,
        "result": result.result if result.ready() else None,
    }