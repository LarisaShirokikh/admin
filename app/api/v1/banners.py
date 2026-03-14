# app/api/v1/banners.py

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.exceptions import raise_404
from app.crud import banners as crud
from app.schemas.banner import BannerListResponse, BannerAdminResponse

router = APIRouter()


@router.get("/active/", response_model=BannerListResponse)
async def get_active_banners(db: AsyncSession = Depends(get_db)):
    banners = await crud.get_active(db)
    return {"items": banners, "total": len(banners)}


