import shutil
import tempfile
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.product import ProductDetail, ProductCreate
from app.crud.product import get_all_products, create_product, get_all_products_filtered, get_product_by_id
from app.deps import get_db
from typing import List, Optional
from app.models.product_ranking import ProductRanking

from app.worker.tasks import import_csv_task

router = APIRouter()

@router.get("/", response_model=List[ProductDetail])
async def list_products(
    db: AsyncSession = Depends(get_db),
    brand_id: Optional[int] = Query(None, description="ID бренда для фильтрации"),
    category_id: Optional[int] = Query(None, description="ID категории для фильтрации"),
    catalog_id: Optional[int] = Query(None, description="ID каталога для фильтрации"),
    price_from: Optional[float] = Query(None, description="Минимальная цена"),
    price_to: Optional[float] = Query(None, description="Максимальная цена"),
):
    """Получение списка продуктов с возможностью фильтрации"""
    return await get_all_products_filtered(
        db=db,
        brand_id=brand_id,  # Изменено с manufacturer_id на brand_id
        category_id=category_id,
        catalog_id=catalog_id,
        price_from=price_from,
        price_to=price_to,
    )

@router.post("/", response_model=ProductDetail)
async def add_product(product: ProductCreate, db: AsyncSession = Depends(get_db)):
    """Добавление нового продукта"""
    return await create_product(db, product, auto_commit=True)

@router.post("/import")
async def import_csv(file: UploadFile = File(...)):
    """Импорт продуктов из CSV-файла"""
    if not file.filename.endswith('.csv'):
        raise HTTPException(400, "Файл должен быть в формате CSV")
        
    temp = tempfile.NamedTemporaryFile(delete=False)
    with temp as f:
        shutil.copyfileobj(file.file, f)

    import_csv_task.delay(temp.name)
    return {"status": "Импорт запущен в фоне", "filename": file.filename}

@router.get("/{product_id}", response_model=ProductDetail)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    """Получение продукта по ID"""
    product = await get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Продукт не найден")
    return product