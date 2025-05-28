from sqlalchemy.ext.asyncio import AsyncSession
from app.models.import_log import ImportLog
from app.schemas.import_log import ImportLogCreate

async def create_import_log(db: AsyncSession, filename: str, rows: int, status="in_progress", message=None):
    log_data = ImportLogCreate(filename=filename, rows=rows, status=status, message=message)
    log = ImportLog(**log_data.model_dump())
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log

async def update_import_log_status(db: AsyncSession, log_id: int, status: str, message: str = None):
    log = await db.get(ImportLog, log_id)
    if log:
        log.status = status
        if message:
            log.message = message
        await db.commit()
        await db.refresh(log)
    return log