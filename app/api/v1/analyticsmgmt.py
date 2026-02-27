# app/api/v1/analyticsmgmt.py
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_current_active_admin
from app.models.analytics import AnalyticsEvent, AnalyticsDailySummary, AnalyticsSession
from app.models.product import Product
from app.models.product_ranking import ProductRanking

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/summary")
async def get_analytics_summary(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_admin),
):
    since = datetime.utcnow() - timedelta(days=days)

    # Total events by type
    type_counts = (await db.execute(
        select(AnalyticsEvent.event_type, func.count())
        .where(AnalyticsEvent.created_at >= since)
        .group_by(AnalyticsEvent.event_type)
    )).all()

    # Unique sessions
    sessions_count = (await db.execute(
        select(func.count(func.distinct(AnalyticsEvent.session_id)))
        .where(AnalyticsEvent.created_at >= since)
    )).scalar() or 0

    # Events per day
    daily_stats = (await db.execute(
        select(
            func.date(AnalyticsEvent.created_at).label("day"),
            AnalyticsEvent.event_type,
            func.count().label("cnt"),
        )
        .where(AnalyticsEvent.created_at >= since)
        .group_by(text("day"), AnalyticsEvent.event_type)
        .order_by(text("day"))
    )).all()

    return {
        "period_days": days,
        "totals": {row[0]: row[1] for row in type_counts},
        "unique_sessions": sessions_count,
        "daily": [
            {"date": str(row.day), "event_type": row.event_type, "count": row.cnt}
            for row in daily_stats
        ],
    }


@router.get("/top-products")
async def get_top_products(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_admin),
):
    since = datetime.utcnow() - timedelta(days=days)

    rows = (await db.execute(
        select(
            AnalyticsEvent.product_id,
            Product.name,
            Product.slug,
            func.count().label("total_events"),
            func.count().filter(AnalyticsEvent.event_type == "view").label("views"),
            func.count().filter(AnalyticsEvent.event_type == "impression").label("impressions"),
            func.count().filter(AnalyticsEvent.event_type == "interaction").label("interactions"),
        )
        .join(Product, Product.id == AnalyticsEvent.product_id)
        .where(AnalyticsEvent.created_at >= since)
        .group_by(AnalyticsEvent.product_id, Product.name, Product.slug)
        .order_by(desc("total_events"))
        .limit(limit)
    )).all()

    return [
        {
            "product_id": r.product_id,
            "name": r.name,
            "slug": r.slug,
            "total_events": r.total_events,
            "views": r.views,
            "impressions": r.impressions,
            "interactions": r.interactions,
        }
        for r in rows
    ]


@router.get("/rankings")
async def get_product_rankings(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_admin),
):
    rows = (await db.execute(
        select(
            ProductRanking.product_id,
            ProductRanking.ranking_score,
            ProductRanking.impressions_count,
            ProductRanking.updated_at,
            Product.name,
            Product.slug,
        )
        .join(Product, Product.id == ProductRanking.product_id)
        .order_by(desc(ProductRanking.ranking_score))
        .limit(limit)
    )).all()

    return [
        {
            "product_id": r.product_id,
            "name": r.name,
            "slug": r.slug,
            "ranking_score": r.ranking_score,
            "impressions_count": r.impressions_count,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]