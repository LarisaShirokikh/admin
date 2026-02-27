# app/crud/analytics.py
import logging
import uuid as uuid_mod
from datetime import datetime, date
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import AnalyticsEvent, AnalyticsSession, AnalyticsDailySummary

logger = logging.getLogger(__name__)


async def create_event(
    db: AsyncSession,
    *,
    product_id: int,
    event_type: str,
    event_subtype: str | None = None,
    event_data: dict | None = None,
    session_id: str | None = None,
    user_agent: str = "",
    device_type: str = "unknown",
    referrer: str = "",
    page_url: str = "",
    ip_address: str = "",
) -> AnalyticsEvent:
    event = AnalyticsEvent(
        product_id=product_id,
        event_type=event_type,
        event_subtype=event_subtype,
        event_data=event_data or {},
        session_id=session_id or str(uuid_mod.uuid4()),
        user_agent=user_agent,
        device_type=device_type,
        referrer=referrer,
        page_url=page_url,
        ip_address=ip_address,
        created_at=datetime.utcnow(),
    )
    db.add(event)
    await db.commit()
    return event


async def create_impression_events(
    db: AsyncSession,
    *,
    product_ids: List[int],
    page_url: str = "",
    user_agent: str = "",
    ip_address: str = "",
) -> int:
    session_id = str(uuid_mod.uuid4())
    now = datetime.utcnow()
    events = [
        AnalyticsEvent(
            product_id=pid,
            event_type="impression",
            event_subtype="card_view",
            event_data={"page_url": page_url},
            session_id=session_id,
            user_agent=user_agent,
            device_type="unknown",
            page_url=page_url,
            ip_address=ip_address,
            created_at=now,
        )
        for pid in product_ids[:50]
    ]
    db.add_all(events)
    await db.commit()
    logger.info(f"Tracked {len(events)} impressions from {ip_address}")
    return len(events)


async def update_daily_summary(
    db: AsyncSession,
    *,
    product_id: int,
    event_type: str,
) -> None:
    today = date.today()
    result = await db.execute(
        select(AnalyticsDailySummary).where(
            AnalyticsDailySummary.product_id == product_id,
            func.date(AnalyticsDailySummary.date) == today,
        )
    )
    summary = result.scalar_one_or_none()

    if summary:
        if event_type == "view":
            summary.views_count += 1
        elif event_type == "impression":
            summary.detail_views_count += 1
        elif event_type == "interaction":
            summary.interactions_count += 1
        summary.updated_at = datetime.utcnow()
    else:
        summary = AnalyticsDailySummary(
            product_id=product_id,
            date=datetime(today.year, today.month, today.day),
            views_count=1 if event_type == "view" else 0,
            detail_views_count=1 if event_type == "impression" else 0,
            interactions_count=1 if event_type == "interaction" else 0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(summary)

    await db.commit()