from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.dependencies import get_db
from app.core.exceptions import raise_404
from app.models.catalog import Catalog
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.brand import Brand
from app.models.category import Category
from app.schemas.catalog import CatalogResponse

router = APIRouter()


def _serialize_product_card(product: Product) -> dict:
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


@router.get("/", response_model=List[CatalogResponse])
@router.get("/list", response_model=List[CatalogResponse])
async def get_catalogs(
    is_active: Optional[bool] = Query(True),
    db: AsyncSession = Depends(get_db),
):
    query = select(Catalog).order_by(Catalog.name)
    if is_active is not None:
        query = query.where(Catalog.is_active == is_active)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/paginated")
async def get_catalogs_paginated(
    is_active: Optional[bool] = Query(True),
    search: Optional[str] = None,
    sort: str = Query("name", pattern="^(name|newest|popular)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(Catalog)
    count_query = select(func.count(Catalog.id))

    filters = []
    if is_active is not None:
        filters.append(Catalog.is_active == is_active)
    if search:
        filters.append(Catalog.name.ilike(f"%{search}%"))

    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))

    sort_map = {
        "name": Catalog.name.asc(),
        "newest": Catalog.created_at.desc(),
        "popular": Catalog.name.asc(),
    }
    query = query.order_by(sort_map.get(sort, Catalog.name.asc()))

    total = (await db.execute(count_query)).scalar() or 0
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    catalogs = result.scalars().all()

    return {
        "items": [CatalogResponse.model_validate(c).model_dump() for c in catalogs],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get("/by-category/{category_slug}")
async def get_catalogs_by_category(
    category_slug: str = Path(...),
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    cat_result = await db.execute(
        select(Category).where(Category.slug == category_slug, Category.is_active == True)
    )
    category = cat_result.scalar_one_or_none()
    if not category:
        raise_404(entity="Category", id=category_slug)

    count_query = select(func.count(Catalog.id)).where(
        and_(Catalog.category_id == category.id, Catalog.is_active == True)
    )
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * per_page
    query = (
        select(Catalog)
        .where(and_(Catalog.category_id == category.id, Catalog.is_active == True))
        .order_by(Catalog.name)
        .offset(offset)
        .limit(per_page)
    )
    result = await db.execute(query)
    catalogs = result.scalars().all()

    return {
        "items": [CatalogResponse.model_validate(c).model_dump() for c in catalogs],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get("/{slug}", response_model=CatalogResponse)
async def get_catalog_by_slug(
    slug: str = Path(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Catalog).where(Catalog.slug == slug, Catalog.is_active == True)
    )
    catalog = result.scalar_one_or_none()
    if not catalog:
        raise_404(entity="Catalog", id=slug)
    return catalog


@router.get("/{slug}/products")
async def get_catalog_with_products(
    slug: str = Path(...),
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Catalog).where(Catalog.slug == slug, Catalog.is_active == True)
    )
    catalog = result.scalar_one_or_none()
    if not catalog:
        raise_404(entity="Catalog", id=slug)

    count_query = select(func.count(Product.id)).where(
        and_(Product.catalog_id == catalog.id, Product.is_active == True)
    )
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * per_page
    products_query = (
        select(Product)
        .options(joinedload(Product.product_images), joinedload(Product.brand))
        .where(and_(Product.catalog_id == catalog.id, Product.is_active == True))
        .order_by(Product.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    products_result = await db.execute(products_query)
    products = products_result.unique().scalars().all()

    return {
        "catalog": CatalogResponse.model_validate(catalog).model_dump(),
        "products": [_serialize_product_card(p) for p in products],
        "total": total,
        "pagination": {"page": page, "per_page": per_page, "total": total},
    }
