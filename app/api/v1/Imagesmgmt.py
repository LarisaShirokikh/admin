import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_current_superuser
from app.models.admin import AdminUser
from app.models.product_image import ProductImage
from app.services.image_service import ImageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/images", tags=["images"])


@router.get("/stats")
async def get_image_stats(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_superuser),
):
    total = await db.execute(select(func.count(ProductImage.id)))
    local = await db.execute(
        select(func.count(ProductImage.id)).where(ProductImage.is_local == True)
    )
    external = await db.execute(
        select(func.count(ProductImage.id)).where(
            ProductImage.is_local == False,
            ProductImage.url.like("http%"),
        )
    )
    failed = await db.execute(
        select(func.count(ProductImage.id)).where(
            ProductImage.download_error.isnot(None)
        )
    )

    disk = ImageService.get_disk_usage()

    return {
        "total_images": total.scalar_one(),
        "local_images": local.scalar_one(),
        "external_images": external.scalar_one(),
        "failed_downloads": failed.scalar_one(),
        "disk_usage": disk,
    }


@router.post("/migrate")
async def start_migration(
    batch_size: int = 50,
    _: AdminUser = Depends(get_current_superuser),
):
    from app.worker.tasks import migrate_external_images_task

    task = migrate_external_images_task.delay(batch_size)
    return {
        "task_id": task.id,
        "message": f"Миграция запущена (batch_size={batch_size})",
    }


@router.get("/migrate/{task_id}")
async def get_migration_status(
    task_id: str,
    _: AdminUser = Depends(get_current_superuser),
):
    from celery.result import AsyncResult

    result = AsyncResult(task_id)
    response = {"task_id": task_id, "status": result.status}

    if hasattr(result, "info") and isinstance(result.info, dict):
        response.update(result.info)

    if result.ready():
        response["result"] = result.result if result.successful() else str(result.result)

    return response


@router.post("/retry-failed")
async def retry_failed_images(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_superuser),
):
    from sqlalchemy import update as sql_update
    from app.worker.tasks import migrate_external_images_task

    # Сбрасываем download_error для повторной попытки
    result = await db.execute(
        sql_update(ProductImage)
        .where(ProductImage.download_error.isnot(None))
        .values(download_error=None, is_local=False)
    )
    await db.commit()

    count = result.rowcount
    if count > 0:
        task = migrate_external_images_task.delay(50)
        return {
            "reset_count": count,
            "task_id": task.id,
            "message": f"Сброшено {count} ошибок, миграция перезапущена",
        }

    return {"reset_count": 0, "message": "Нет неудачных картинок"}