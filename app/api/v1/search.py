# app/api/v1/search/router.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional

from app.core.dependencies import get_db
from app.models import Product, ProductImage
from app.models.brand import Brand
from app.models.catalog import Catalog
from app.models.category import Category
from app.schemas.search import SearchResponse, SearchSuggestionsResponse

router = APIRouter()


@router.get("/", response_model=SearchResponse)
async def search_products(
    q: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=100),
    sort: str = Query("popular"),
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    category_id: Optional[str] = None,
    brand_slug: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    search_term = f"%{q.strip()}%"

    conditions = [
        Product.is_active == True,
        (Product.name.ilike(search_term) | Product.description.ilike(search_term)),
    ]
    if min_price is not None:
        conditions.append(Product.price >= min_price)
    if max_price is not None:
        conditions.append(Product.price <= max_price)
    if brand_slug:
        conditions.append(Product.brand.has(Brand.slug == brand_slug))

    # Count
    count_q = select(func.count(Product.id)).where(*conditions)
    total = (await db.execute(count_q)).scalar() or 0

    # Query
    query = (
        select(Product)
        .options(
            selectinload(Product.brand),
            selectinload(Product.catalog),
            selectinload(Product.product_images),
        )
        .where(*conditions)
    )

    if sort == "price_asc":
        query = query.order_by(Product.price.asc())
    elif sort == "price_desc":
        query = query.order_by(Product.price.desc())
    elif sort == "newest":
        query = query.order_by(Product.created_at.desc())
    else:
        query = query.order_by(Product.views_count.desc().nullslast(), Product.created_at.desc())

    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    products = result.scalars().all()

    return {
        "items": products,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if total else 0,
    }


@router.get("/suggestions/", response_model=SearchSuggestionsResponse)
async def get_search_suggestions(
    q: str,
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    if len(q.strip()) < 2:
        return {"suggestions": []}

    search_term = f"%{q.strip()}%"

    query = (
        select(
            Product.id,
            Product.name,
            Product.slug,
            Category.name.label("category_name"),
        )
        .outerjoin(Product.categories)
        .where(Product.is_active == True, Product.name.ilike(search_term))
        .order_by(Product.popularity_score.desc().nullslast(), Product.created_at.desc())
        .limit(limit)
    )

    result = await db.execute(query)
    rows = result.all()

    # Get first image for each product
    product_ids = [r.id for r in rows]
    images_q = (
        select(ProductImage.product_id, ProductImage.url)
        .where(ProductImage.product_id.in_(product_ids))
        .distinct(ProductImage.product_id)
    )
    images_result = await db.execute(images_q)
    image_map = {r.product_id: r.url for r in images_result.all()}

    suggestions = [
        {
            "id": r.id,
            "name": r.name,
            "slug": r.slug,
            "image": image_map.get(r.id),
            "category": r.category_name,
        }
        for r in rows
    ]

    return {"suggestions": suggestions}