import shutil
import tempfile
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.product import ProductDetail, ProductCreate
from app.crud.product import get_all_products, create_product, get_all_products_filtered, get_product_by_id, get_product_by_title
from app.deps import get_db
from typing import List, Optional

from app.worker.tasks import import_csv_task

router = APIRouter()

@router.get("/", response_model=List[ProductDetail])
async def list_products(db: AsyncSession = Depends(get_db)):
    """Получение списка всех продуктов"""
    return await get_all_products(db)

@router.get("/by-title/{title}", response_model=ProductDetail)
async def get_product_by_title_route(title: str, db: AsyncSession = Depends(get_db)):
    """Получение продукта по тайтлу"""
    product = await get_product_by_title(db, title)
    if not product:
        raise HTTPException(status_code=404, detail="Продукт с таким тайтлом не найден")
    return product

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