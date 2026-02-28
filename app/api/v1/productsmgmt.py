import logging
import shutil
import tempfile
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_db,
    get_current_active_admin,
    get_current_superuser,
    check_admin_rate_limit,
)
from app.core.exceptions import raise_400, raise_404
from app.crud import productsmgmt as crud
from app.models.admin import AdminUser
from app.schemas.product import (
    BatchUpdateRequest,
    BatchUpdateResponse,
    PriceUpdateRequest,
    PriceUpdateResponse,
    ProductCountRequest,
    ProductCreate,
    ProductDetail,
    ProductFilter,
    ProductImage,
    ProductListItem,
    ProductResponse,
    ProductUpdate,
)
from app.worker.tasks import import_csv_task

router = APIRouter()
logger = logging.getLogger(__name__)


# === GET ===


@router.get("/", response_model=List[ProductListItem])
async def list_products(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    brand_id: Optional[int] = None,
    catalog_id: Optional[int] = None,
    category_id: Optional[int] = None,
    price_from: Optional[float] = Query(None, ge=0),
    price_to: Optional[float] = Query(None, ge=0),
    in_stock: Optional[bool] = None,
    is_active: Optional[bool] = True,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=100)
    return await crud.get_products_list(
        db,
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


@router.get("/stats/summary")
async def get_stats(
    request: Request,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=20)
    return await crud.get_stats(db)


@router.get("/count")
async def get_count(
    request: Request,
    search: Optional[str] = None,
    brand_id: Optional[int] = None,
    catalog_id: Optional[int] = None,
    category_id: Optional[int] = None,
    is_active: Optional[bool] = True,
    in_stock: Optional[bool] = None,
    price_from: Optional[float] = Query(None, ge=0),
    price_to: Optional[float] = Query(None, ge=0),
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    count = await crud.get_count(
        db,
        search=search,
        brand_id=brand_id,
        catalog_id=catalog_id,
        category_id=category_id,
        is_active=is_active,
        in_stock=in_stock,
        price_from=price_from,
        price_to=price_to,
    )
    return {"count": count}


@router.get("/filter", response_model=List[ProductListItem])
async def filter_products(
    request: Request,
    product_filter: ProductFilter = Depends(),
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    return await crud.get_filtered(
        db,
        brand_id=product_filter.brand_id,
        category_id=product_filter.category_id,
        catalog_id=product_filter.catalog_id,
        price_from=product_filter.min_price,
        price_to=product_filter.max_price,
        page=product_filter.page,
        per_page=product_filter.per_page,
    )


@router.get("/by-title/{title}", response_model=ProductDetail)
async def get_by_title(
    request: Request,
    title: str,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    product = await crud.get_by_title(db, title)
    if not product:
        raise_404(entity="Product", id=title)
    return product


@router.get("/by-slug/{slug}", response_model=ProductDetail)
async def get_by_slug(
    request: Request,
    slug: str,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    product = await crud.get_by_slug(db, slug)
    if not product:
        raise_404(entity="Product", id=slug)
    return product


@router.get("/{product_id}", response_model=ProductDetail)
async def get_by_id(
    request: Request,
    product_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    product = await crud.get_by_id(db, product_id)
    if not product:
        raise_404(entity="Product", id=product_id)
    return product


@router.get("/{product_id}/images", response_model=List[ProductImage])
async def get_images(
    request: Request,
    product_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request)
    images = await crud.get_images(db, product_id)
    if images is None:
        raise_404(entity="Product", id=product_id)
    return images


# === CREATE ===


@router.post("/", response_model=ProductDetail, status_code=status.HTTP_201_CREATED)
async def create_product(
    request: Request,
    product: ProductCreate,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=30)
    created = await crud.create(db, product)
    if not created:
        raise_400("Failed to create product")
    return created


@router.post("/create-or-update", response_model=ProductDetail)
async def create_or_update(
    request: Request,
    product: ProductCreate,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=30)
    result = await crud.create_or_update(db, product)
    if not result:
        raise_400("Failed to create or update product")
    return result


@router.post("/import")
async def import_csv(
    request: Request,
    file: UploadFile = File(...),
    current_user: AdminUser = Depends(get_current_active_admin),
):
    check_admin_rate_limit(request, max_requests=5, window_minutes=5)
    if not file.filename.endswith(".csv"):
        raise_400("File must be CSV")
    logger.info("CSV import by %s: %s", current_user.username, file.filename)
    tmp = tempfile.NamedTemporaryFile(delete=False)
    with tmp as f:
        shutil.copyfileobj(file.file, f)
    import_csv_task.delay(tmp.name)
    return {"status": "started", "filename": file.filename}


@router.post("/{product_id}/toggle-status", response_model=ProductResponse)
async def toggle_status(
    request: Request,
    product_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=50)
    product = await crud.toggle_status(db, product_id)
    if not product:
        raise_404(entity="Product", id=product_id)
    return product


# === UPDATE ===


@router.put("/{product_id}", response_model=ProductDetail)
async def update_full(
    request: Request,
    product_id: int,
    product_data: ProductUpdate,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=30)
    updated, err = await crud.update_full(db, product_id, product_data)
    if err == "not_found":
        raise_404(entity="Product", id=product_id)
    if err == "update_failed":
        raise_400("Failed to update product")
    return updated


@router.patch("/batch", response_model=BatchUpdateResponse)
async def batch_update(
    request: Request,
    batch_data: BatchUpdateRequest,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=100)
    if len(batch_data.product_ids) > 100:
        raise_400("Max 100 products per batch")
    update_data = batch_data.update_data.model_dump(exclude_unset=True)
    if not update_data:
        raise_400("No fields to update")
    result = await crud.batch_update(db, batch_data.product_ids, batch_data.update_data)
    return BatchUpdateResponse(**result)


@router.patch("/{product_id}", response_model=ProductDetail)
async def update_partial(
    request: Request,
    product_id: int,
    product_data: ProductUpdate,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=200)
    if not product_data.model_dump(exclude_unset=True):
        raise_400("No fields to update")
    updated, err = await crud.update_partial(db, product_id, product_data)
    if err == "not_found":
        raise_404(entity="Product", id=product_id)
    if err == "update_failed":
        raise_400("Failed to update product")
    return updated


# === PRICES ===


@router.post("/bulk-update-prices", response_model=PriceUpdateResponse)
async def bulk_update_prices(
    request: PriceUpdateRequest,
    current_user: AdminUser = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    return await crud.bulk_update_prices(db, request)


@router.post("/count-for-price-update")
async def count_for_price_update(
    request: ProductCountRequest,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    count = await crud.count_for_price_update(db, request)
    return {"count": count}


@router.post("/batch-delete", status_code=status.HTTP_200_OK)
async def batch_delete(
    request: Request,
    data: dict,
    current_user: AdminUser = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=10)
    product_ids = data.get("product_ids", [])
    if not product_ids:
        raise_400("No product IDs provided")
    if len(product_ids) > 500:
        raise_400("Max 500 products per batch")
    logger.warning("Superuser %s batch deleting %d products", current_user.username, len(product_ids))
    deleted = await crud.batch_delete(db, product_ids)
    return {"deleted": deleted, "requested": len(product_ids)}


@router.delete("/all", status_code=status.HTTP_200_OK)
async def delete_all_products(
    request: Request,
    current_user: AdminUser = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=2, window_minutes=5)
    logger.warning("Superuser %s deleting ALL products", current_user.username)
    deleted = await crud.delete_all(db)
    return {"deleted": deleted}

# === DELETE ===


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    request: Request,
    product_id: int,
    current_user: AdminUser = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=10)
    logger.warning("Superuser %s deleting product %d", current_user.username, product_id)
    result = await crud.delete_hard(db, product_id)
    if result is None:
        raise_404(entity="Product", id=product_id)


@router.delete("/{product_id}/soft", response_model=ProductResponse)
async def soft_delete(
    request: Request,
    product_id: int,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=30)
    product = await crud.delete_soft(db, product_id)
    if not product:
        raise_404(entity="Product", id=product_id)
    return product


