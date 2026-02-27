import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.dependencies import get_db
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.brand import Brand
from app.models.catalog import Catalog
from app.models.category import Category
from app.models.product_ranking import ProductRanking as PRModel

router = APIRouter()
logger = logging.getLogger(__name__)


def _serialize_product_card(product: Product) -> Dict[str, Any]:
    main_image = None
    if product.product_images:
        main = next((img for img in product.product_images if img.is_main), None)
        main_image = main.url if main else product.product_images[0].url

    return {
        "id": product.id,
        "name": product.name,
        "slug": product.slug,
        "price": float(product.price) if product.price else 0.0,
        "discount_price": float(product.discount_price) if product.discount_price else None,
        "image": main_image,
        "brand": product.brand.name if product.brand else None,
        "in_stock": product.in_stock,
    }


def _serialize_product_detail(product: Product) -> Dict[str, Any]:
    images = []
    for img in (product.product_images or []):
        images.append({
            "id": img.id,
            "url": img.url,
            "is_main": getattr(img, "is_main", False),
            "alt_text": getattr(img, "alt_text", None),
        })

    return {
        "id": product.id,
        "name": product.name,
        "slug": product.slug,
        "description": product.description,
        "price": float(product.price) if product.price else 0.0,
        "discount_price": float(product.discount_price) if product.discount_price else None,
        "in_stock": getattr(product, "in_stock", False),
        "is_new": getattr(product, "is_new", False),
        "type": getattr(product, "type", None),
        "rating": getattr(product, "rating", 0.0),
        "review_count": getattr(product, "review_count", 0),
        "brand": {
            "id": product.brand.id,
            "name": product.brand.name,
            "slug": getattr(product.brand, "slug", None),
        } if product.brand else None,
        "catalog": {
            "id": product.catalog.id,
            "name": product.catalog.name,
            "slug": getattr(product.catalog, "slug", None),
        } if product.catalog else None,
        "categories": [
            {"id": c.id, "name": c.name, "slug": getattr(c, "slug", None)}
            for c in (product.categories or [])
        ],
        "images": images,
    }


def _base_product_query():
    return select(Product).options(
        joinedload(Product.product_images),
        joinedload(Product.brand),
        joinedload(Product.catalog),
    ).where(Product.is_active == True)


# --- Endpoints ---


@router.get("/")
async def get_products(
    category_slug: Optional[str] = None,
    brand_slug: Optional[str] = None,
    catalog_slug: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    in_stock: Optional[bool] = None,
    search: Optional[str] = None,
    sort: str = Query("newest", pattern="^(newest|price_asc|price_desc|popular)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = _base_product_query()
    count_query = select(func.count(Product.id)).where(Product.is_active == True)

    filters = []
    if category_slug:
        filters.append(Product.categories.any(Category.slug == category_slug))
    if brand_slug:
        filters.append(Product.brand.has(Brand.slug == brand_slug))
    if catalog_slug:
        filters.append(Product.catalog.has(Catalog.slug == catalog_slug))
    if min_price is not None:
        filters.append(Product.price >= min_price)
    if max_price is not None:
        filters.append(Product.price <= max_price)
    if in_stock is not None:
        filters.append(Product.in_stock == in_stock)
    if search:
        term = f"%{search}%"
        filters.append(Product.name.ilike(term))

    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))

    sort_map = {
        "newest": Product.created_at.desc(),
        "price_asc": Product.price.asc(),
        "price_desc": Product.price.desc(),
        "popular": Product.rating.desc(),
    }
    query = query.order_by(sort_map.get(sort, Product.created_at.desc()))

    total = (await db.execute(count_query)).scalar() or 0
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    products = result.unique().scalars().all()

    return {
        "items": [_serialize_product_card(p) for p in products],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get("/slugs")
async def get_product_slugs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Product.slug).where(Product.is_active == True)
    )
    return [row[0] for row in result.fetchall()]


@router.get("/featured")
async def get_featured_products(
    limit: int = Query(8, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):


    query = (
        select(Product)
        .options(
            joinedload(Product.product_images),
            joinedload(Product.brand),
            joinedload(Product.catalog),
        )
        .outerjoin(PRModel, PRModel.product_id == Product.id)
        .where(Product.is_active == True)
        .order_by(
            desc(func.coalesce(PRModel.ranking_score, 0)),
            Product.rating.desc(),
            Product.created_at.desc(),
        )
        .limit(limit)
    )
    result = await db.execute(query)
    products = result.unique().scalars().all()
    return [_serialize_product_card(p) for p in products]


@router.get("/new")
async def get_new_products(
    limit: int = Query(8, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    query = (
        _base_product_query()
        .order_by(Product.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    products = result.unique().scalars().all()
    return [_serialize_product_card(p) for p in products]


@router.get("/discounted")
async def get_discounted_products(
    limit: int = Query(8, ge=1, le=20),
    min_discount_percent: int = Query(5, ge=0, le=90),
    db: AsyncSession = Depends(get_db),
):
    discount_filter = (
        ((Product.price - Product.discount_price) / Product.price) * 100
        >= min_discount_percent
    )
    query = (
        _base_product_query()
        .where(and_(
            Product.discount_price.is_not(None),
            Product.discount_price < Product.price,
            discount_filter,
        ))
        .order_by(desc((Product.price - Product.discount_price) / Product.price))
        .limit(limit)
    )
    result = await db.execute(query)
    products = result.unique().scalars().all()

    items = []
    for p in products:
        card = _serialize_product_card(p)
        card["discount_percent"] = round(
            (float(p.price) - float(p.discount_price)) / float(p.price) * 100
        )
        card["savings"] = round(float(p.price) - float(p.discount_price), 2)
        items.append(card)
    return items


@router.get("/price-range")
async def get_price_range(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            func.min(Product.price).label("min_price"),
            func.max(Product.price).label("max_price"),
        ).where(Product.is_active == True)
    )
    row = result.first()
    return {
        "min": float(row.min_price) if row.min_price else 0.0,
        "max": float(row.max_price) if row.max_price else 100000.0,
    }


@router.get("/{slug}")
async def get_product_by_slug(
    slug: str = Path(...),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Product)
        .options(
            joinedload(Product.product_images),
            joinedload(Product.brand),
            joinedload(Product.catalog),
            joinedload(Product.categories),
        )
        .where(and_(Product.slug == slug, Product.is_active == True))
    )
    result = await db.execute(query)
    product = result.unique().scalar_one_or_none()

    if not product:
        raise HTTPException(404, "Product not found")

    return _serialize_product_detail(product)
