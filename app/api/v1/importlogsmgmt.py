from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.schemas.import_log import ImportLogRead
from app.models.import_log import ImportLog
from app.core.dependencies import get_db
from sqlalchemy import select

router = APIRouter()

@router.get("/", response_model=List[ImportLogRead])
async def get_import_logs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ImportLog).order_by(ImportLog.created_at.desc()))
    return result.scalars().all()

@router.get("/{log_id}", response_model=ImportLogRead)
async def get_import_log(log_id: int, db: AsyncSession = Depends(get_db)):
    log = await db.get(ImportLog, log_id)
    return log