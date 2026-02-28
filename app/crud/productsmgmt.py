import logging
from typing import Any, List, Optional

from sqlalchemy import and_, select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.product import Product
from app.models.attributes import product_categories
from app.models.product_image import ProductImage
from app.crud import product as base_crud

logger = logging.getLogger(__name__)


def attach_main_image(product) -> None:
    if hasattr(product, "product_images") and product.product_images:
        main = next(
            (img for img in product.product_images if getattr(img, "is_main", False)),
            None,
        )
        product.main_image = main.url if main else product.product_images[0].url
    else:
        product.main_image = None


async def get_products_list(
    db: AsyncSession,
    *,
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    brand_id: Optional[int] = None,
    catalog_id: Optional[int] = None,
    category_id: Optional[int] = None,
    price_from: Optional[float] = None,
    price_to: Optional[float] = None,
    in_stock: Optional[bool] = None,
    is_active: Optional[bool] = True,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> list:
    products, _ = await base_crud.get_products_paginated_with_relations(
        db=db,
        skip=skip,
        limit=limit,
        search=search,
        brand_id=brand_id,
        catalog_id=catalog_id,
        category_id=category_id,
        price_from=price_from,
        price_to=price_to,
        in_stock=in_stock,
        is_active=is_active,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    for p in products:
        attach_main_image(p)
    return products


async def get_stats(db: AsyncSession) -> dict:
    total = await base_crud.get_products_count(db, is_active=None)
    active = await base_crud.get_products_count(db, is_active=True)
    return {
        "total_products": total,
        "active_products": active,
        "inactive_products": total - active,
        "products_with_brand": await base_crud.get_products_count(db, has_brand=True),
        "products_without_brand": await base_crud.get_products_count(db, has_brand=False),
        "products_with_catalog": await base_crud.get_products_count(db, has_catalog=True),
        "products_without_catalog": await base_crud.get_products_count(db, has_catalog=False),
        "products_in_stock": await base_crud.get_products_count(db, in_stock=True),
        "products_out_of_stock": await base_crud.get_products_count(db, in_stock=False),
    }


async def get_count(
    db: AsyncSession,
    *,
    search: Optional[str] = None,
    brand_id: Optional[int] = None,
    catalog_id: Optional[int] = None,
    category_id: Optional[int] = None,
    is_active: Optional[bool] = True,
    in_stock: Optional[bool] = None,
    price_from: Optional[float] = None,
    price_to: Optional[float] = None,
) -> int:
    return await base_crud.get_products_count(
        db=db,
        search=search,
        brand_id=brand_id,
        catalog_id=catalog_id,
        category_id=category_id,
        is_active=is_active,
        in_stock=in_stock,
        price_from=price_from,
        price_to=price_to,
    )


async def get_filtered(
    db: AsyncSession,
    *,
    brand_id: Optional[int] = None,
    category_id: Optional[int] = None,
    catalog_id: Optional[int] = None,
    price_from: Optional[float] = None,
    price_to: Optional[float] = None,
    page: int = 1,
    per_page: int = 20,
) -> list:
    products = await base_crud.get_all_products_filtered_with_relations(
        db=db,
        brand_id=brand_id,
        category_id=category_id,
        catalog_id=catalog_id,
        price_from=price_from,
        price_to=price_to,
    )
    start = (page - 1) * per_page
    end = start + per_page
    for p in products[start:end]:
        attach_main_image(p)
    return products[start:end]


async def get_by_title(db: AsyncSession, title: str):
    return await base_crud.get_product_by_title(db, title)


async def get_by_slug(db: AsyncSession, slug: str):
    product = await base_crud.get_product_by_slug_with_relations(db, slug)
    if product:
        attach_main_image(product)
    return product


async def get_by_id(db: AsyncSession, product_id: int):
    product = await base_crud.get_product_by_id_with_relations(db, product_id)
    if product:
        attach_main_image(product)
    return product


async def get_images(db: AsyncSession, product_id: int) -> list:
    product = await base_crud.get_product_by_id_with_relations(db, product_id)
    if not product:
        return None
    if product.product_images:
        return product.product_images
    result = await db.execute(
        select(ProductImage)
        .where(ProductImage.product_id == product_id)
        .order_by(ProductImage.is_main.desc(), ProductImage.id)
    )
    return result.scalars().all()


async def create(db: AsyncSession, product_data):
    created = await base_crud.create_product_with_relations(db, product_data, auto_commit=True)
    if created:
        attach_main_image(created)
    return created


async def create_or_update(db: AsyncSession, product_data):
    result = await base_crud.create_or_update_product(db, product_data)
    if not result:
        return None
    await db.commit()
    full = await base_crud.get_product_by_id_with_relations(db, result.id)
    if full:
        attach_main_image(full)
    return full


async def toggle_status(db: AsyncSession, product_id: int):
    product = await base_crud.toggle_product_status(db, product_id)
    if product:
        await db.commit()
    return product


async def update_full(db: AsyncSession, product_id: int, product_data):
    existing = await base_crud.get_product_by_id_with_relations(db, product_id)
    if not existing:
        return None, "not_found"
    updated = await base_crud.update_product_with_relations(db, product_id, product_data)
    if not updated:
        return None, "update_failed"
    await db.commit()
    attach_main_image(updated)
    return updated, None


async def update_partial(db: AsyncSession, product_id: int, product_data):
    existing = await base_crud.get_product_by_id_with_relations(db, product_id)
    if not existing:
        return None, "not_found"
    updated = await base_crud.update_product_with_relations(db, product_id, product_data)
    if not updated:
        return None, "update_failed"
    await db.commit()
    attach_main_image(updated)
    return updated, None


async def batch_update(
    db: AsyncSession,
    product_ids: List[int],
    update_data,
) -> dict:
    success_count = 0
    failed_count = 0
    updated_products = []
    failed_products = []

    for pid in product_ids:
        try:
            existing = await base_crud.get_product_by_id_with_relations(db, pid)
            if not existing:
                failed_products.append({"product_id": pid, "error": "Not found"})
                failed_count += 1
                continue
            result = await base_crud.update_product_with_relations(db, pid, update_data)
            if result:
                updated_products.append(pid)
                success_count += 1
            else:
                failed_products.append({"product_id": pid, "error": "Update failed"})
                failed_count += 1
        except Exception as e:
            failed_products.append({"product_id": pid, "error": str(e)})
            failed_count += 1

    await db.commit()
    return {
        "success_count": success_count,
        "failed_count": failed_count,
        "updated_products": updated_products,
        "failed_products": failed_products,
    }


async def bulk_update_prices(db: AsyncSession, request_data) -> Any:
    return await base_crud.bulk_update_product_prices(
        db=db,
        scope=request_data.scope,
        scope_id=request_data.scope_id,
        price_type=request_data.price_type,
        change_type=request_data.change_type,
        change_value=request_data.change_value,
        direction=request_data.direction,
        only_active=request_data.only_active,
        only_in_stock=request_data.only_in_stock,
        price_range=request_data.price_range,
    )


async def count_for_price_update(db: AsyncSession, request_data) -> int:
    query = select(func.count(Product.id))
    conditions = []

    if request_data.scope == "brand" and request_data.scope_id:
        conditions.append(Product.brand_id == request_data.scope_id)
    elif request_data.scope == "category" and request_data.scope_id:
        query = (
            query.select_from(Product)
            .join(Product.categories)
            .where(Category.id == request_data.scope_id)
        )
    elif request_data.scope == "catalog" and request_data.scope_id:
        conditions.append(Product.catalog_id == request_data.scope_id)

    if request_data.only_active:
        conditions.append(Product.is_active == True)
    if request_data.only_in_stock:
        conditions.append(Product.in_stock == True)
    if request_data.price_range:
        if request_data.price_range.get("from"):
            conditions.append(Product.price >= request_data.price_range["from"])
        if request_data.price_range.get("to"):
            conditions.append(Product.price <= request_data.price_range["to"])

    if conditions:
        query = query.where(and_(*conditions))

    result = await db.execute(query)
    return result.scalar() or 0


async def delete_hard(db: AsyncSession, product_id: int) -> bool:
    existing = await base_crud.get_product_by_id_with_relations(db, product_id)
    if not existing:
        return None
    success = await base_crud.delete_product(db, product_id)
    if success:
        await db.commit()
    return success


async def delete_soft(db: AsyncSession, product_id: int):
    product = await base_crud.soft_delete_product(db, product_id)
    if product:
        await db.commit()
    return product




async def batch_delete(db: AsyncSession, product_ids: List[int]) -> int:
    await db.execute(
        delete(ProductImage).where(ProductImage.product_id.in_(product_ids))
    )
    await db.execute(
        delete(product_categories).where(product_categories.c.product_id.in_(product_ids))
    )
    result = await db.execute(
        delete(Product).where(Product.id.in_(product_ids))
    )
    await db.commit()
    return result.rowcount


async def delete_all(db: AsyncSession) -> int:
    await db.execute(delete(ProductImage))
    await db.execute(delete(product_categories))
    result = await db.execute(delete(Product))
    await db.commit()
    return result.rowcount