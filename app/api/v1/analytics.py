# app/api/v1/analytics.py
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.exceptions import raise_400
from app.crud import analytics as analytics_crud
from app.crud.product_ranking import ProductRanking

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    return getattr(request.client, "host", "unknown")


def _extract_session_data(request: Request, **kwargs) -> dict:
    data = {k: v for k, v in kwargs.items() if v is not None}
    data["user_agent"] = data.get("user_agent") or request.headers.get("User-Agent", "")
    data["ip_address"] = _get_client_ip(request)
    return data


# --- Endpoints ---


@router.get("/product/{product_id}/view")
async def track_product_view(
    request: Request,
    product_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    page_type: Optional[str] = None,
    location: Optional[str] = None,
    referrer: Optional[str] = None,
    device_type: Optional[str] = None,
    url: Optional[str] = None,
    timestamp: Optional[str] = None,
    session_id: Optional[str] = None,
    user_agent: Optional[str] = None,
):
    session_data = _extract_session_data(
        request,
        page_type=page_type, location=location, referrer=referrer,
        device_type=device_type, url=url, timestamp=timestamp,
        session_id=session_id, user_agent=user_agent,
    )

    background_tasks.add_task(
        ProductRanking.process_product_view, db, product_id, session_data,
    )
    return {"success": True}


@router.get("/product/{product_id}/interaction")
async def track_product_interaction(
    request: Request,
    product_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    interaction_type: str = Query(...),
    duration_seconds: Optional[int] = None,
    image_index: Optional[int] = None,
    action: Optional[str] = None,
    button_text: Optional[str] = None,
    page_type: Optional[str] = None,
    location: Optional[str] = None,
    referrer: Optional[str] = None,
    device_type: Optional[str] = None,
    url: Optional[str] = None,
    timestamp: Optional[str] = None,
    session_id: Optional[str] = None,
    user_agent: Optional[str] = None,
):
    interaction_data = {
        k: v for k, v in {
            "duration_seconds": duration_seconds,
            "image_index": image_index,
            "action": action,
            "button_text": button_text,
        }.items() if v is not None
    }

    session_data = _extract_session_data(
        request,
        page_type=page_type, location=location, referrer=referrer,
        device_type=device_type, url=url, timestamp=timestamp,
        session_id=session_id, user_agent=user_agent,
    )

    background_tasks.add_task(
        ProductRanking.process_product_interaction,
        db, product_id, interaction_type, interaction_data, session_data,
    )
    return {"success": True}


@router.post("/impressions")
async def track_impressions(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    body = await request.json()
    product_ids = body.get("product_ids", [])
    page_url = body.get("page_url", "")

    if not product_ids:
        raise_400("No product_ids provided")

    ip = _get_client_ip(request)
    ua = request.headers.get("User-Agent", "")

    background_tasks.add_task(
        analytics_crud.create_impression_events,
        db,
        product_ids=product_ids,
        page_url=page_url,
        user_agent=ua,
        ip_address=ip,
    )
    return {"success": True, "count": len(product_ids)}