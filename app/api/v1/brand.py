# app/api/v1/endpoints/brands.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.crud.brand import (
    create_brand, 
    get_brands, 
    get_brand, 
    get_brand_by_slug,
    update_brand, 
    delete_brand
)
from app.schemas.brand import BrandCreate, BrandResponse, BrandUpdate
from app.deps import get_db

router = APIRouter()

@router.get("/", response_model=List[BrandResponse])
async def list_brands(
    skip: int = Query(0, ge=0, description="Number of brands to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of brands to return"),
    db: AsyncSession = Depends(get_db)
):
    """
    Получить список всех брендов с пагинацией
    """
    brands = await get_brands(db, skip=skip, limit=limit)
    return brands

@router.get("/{brand_id}", response_model=BrandResponse)
async def get_brand_by_id(
    brand_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Получить бренд по ID
    """
    brand = await get_brand(db, brand_id)
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Brand with id {brand_id} not found"
        )
    return brand

@router.get("/slug/{slug}", response_model=BrandResponse)
async def get_brand_by_slug_endpoint(
    slug: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Получить бренд по slug
    """
    brand = await get_brand_by_slug(db, slug)
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Brand with slug '{slug}' not found"
        )
    return brand

@router.post("/", response_model=BrandResponse, status_code=status.HTTP_201_CREATED)
async def create_brand_endpoint(
    brand_data: BrandCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Создать новый бренд
    """
    # Проверяем, не существует ли бренд с таким slug (если slug указан)
    if brand_data.slug:
        existing_brand = await get_brand_by_slug(db, brand_data.slug)
        if existing_brand:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Brand with slug '{brand_data.slug}' already exists"
            )
    
    try:
        brand = await create_brand(db, brand_data)
        return brand
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error creating brand: {str(e)}"
        )

@router.put("/{brand_id}", response_model=BrandResponse)
async def update_brand_endpoint(
    brand_id: int,
    brand_data: BrandUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Обновить бренд по ID
    """
    # Проверяем, существует ли бренд
    existing_brand = await get_brand(db, brand_id)
    if not existing_brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Brand with id {brand_id} not found"
        )
    
    # Если обновляется slug, проверяем уникальность
    if brand_data.slug and brand_data.slug != existing_brand.slug:
        brand_with_slug = await get_brand_by_slug(db, brand_data.slug)
        if brand_with_slug:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Brand with slug '{brand_data.slug}' already exists"
            )
    
    try:
        updated_brand = await update_brand(db, brand_id, brand_data)
        return updated_brand
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error updating brand: {str(e)}"
        )

@router.patch("/{brand_id}", response_model=BrandResponse)
async def partial_update_brand(
    brand_id: int,
    brand_data: BrandUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Частично обновить бренд по ID (алиас для PUT)
    """
    return await update_brand_endpoint(brand_id, brand_data, db)

@router.delete("/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brand_endpoint(
    brand_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Удалить бренд по ID
    """
    success = await delete_brand(db, brand_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Brand with id {brand_id} not found"
        )
    return None

@router.post("/{brand_id}/toggle-status", response_model=BrandResponse)
async def toggle_brand_status(
    brand_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Переключить статус активности бренда
    """
    brand = await get_brand(db, brand_id)
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Brand with id {brand_id} not found"
        )
    
    # Создаем объект для обновления только статуса
    brand_update = BrandUpdate(is_active=not brand.is_active)
    updated_brand = await update_brand(db, brand_id, brand_update)
    
    return updated_brand