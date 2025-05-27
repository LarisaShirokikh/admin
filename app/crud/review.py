# app/crud/review.py
from typing import List, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.review import Review
from app.models.product import Product
from app.schemas.review import ReviewCreate, ReviewUpdate

async def create_review(db: AsyncSession, review: ReviewCreate) -> Review:
    """Создание нового отзыва"""
    db_review = Review(
        product_id=review.product_id,
        author_name=review.author_name,
        rating=review.rating,
        text=review.text,
        is_approved=review.is_approved
    )
    
    db.add(db_review)
    await db.commit()
    await db.refresh(db_review)
    
    # Обновляем рейтинг и количество отзывов товара
    await update_product_rating(db, review.product_id)
    
    return db_review

async def get_review(db: AsyncSession, review_id: int) -> Optional[Review]:
    """Получение отзыва по ID"""
    result = await db.execute(select(Review).where(Review.id == review_id))
    return result.scalar_one_or_none()

async def get_reviews(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[Review]:
    """Получение списка отзывов"""
    result = await db.execute(select(Review).offset(skip).limit(limit))
    return result.scalars().all()

async def get_product_reviews(db: AsyncSession, product_id: int, skip: int = 0, limit: int = 100) -> List[Review]:
    """Получение отзывов для конкретного товара"""
    result = await db.execute(
        select(Review)
        .where(Review.product_id == product_id)
        .where(Review.is_approved == 1)  # Только одобренные отзывы
        .order_by(Review.created_at.desc())  # Сначала новые
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()

async def update_review(db: AsyncSession, review_id: int, review: ReviewUpdate) -> Optional[Review]:
    """Обновление отзыва"""
    db_review = await get_review(db, review_id)
    if not db_review:
        return None
    
    # Запоминаем старый product_id
    old_product_id = db_review.product_id
    
    # Обновляем только переданные поля
    update_data = review.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_review, key, value)
    
    await db.commit()
    await db.refresh(db_review)
    
    # Обновляем рейтинг и количество отзывов товара
    await update_product_rating(db, old_product_id)
    if old_product_id != db_review.product_id:
        await update_product_rating(db, db_review.product_id)
    
    return db_review

async def delete_review(db: AsyncSession, review_id: int) -> bool:
    """Удаление отзыва"""
    db_review = await get_review(db, review_id)
    if not db_review:
        return False
    
    product_id = db_review.product_id
    
    await db.delete(db_review)
    await db.commit()
    
    # Обновляем рейтинг и количество отзывов товара
    await update_product_rating(db, product_id)
    
    return True

async def approve_review(db: AsyncSession, review_id: int) -> bool:
    """Одобрение отзыва"""
    db_review = await get_review(db, review_id)
    if not db_review:
        return False
    
    db_review.is_approved = 1
    await db.commit()
    
    # Обновляем рейтинг и количество отзывов товара
    await update_product_rating(db, db_review.product_id)
    
    return True

async def reject_review(db: AsyncSession, review_id: int) -> bool:
    """Отклонение отзыва"""
    db_review = await get_review(db, review_id)
    if not db_review:
        return False
    
    db_review.is_approved = -1
    await db.commit()
    
    # Обновляем рейтинг и количество отзывов товара
    await update_product_rating(db, db_review.product_id)
    
    return True

async def update_product_rating(db: AsyncSession, product_id: int) -> None:
    """Обновляет рейтинг и количество отзывов товара"""
    # Вычисляем средний рейтинг и количество одобренных отзывов
    result = await db.execute(
        select(
            func.count(Review.id).label("count"),
            func.avg(Review.rating).label("avg_rating")
        )
        .where(Review.product_id == product_id)
        .where(Review.is_approved == 1)  # Только одобренные отзывы
    )
    
    stats = result.first()
    count = stats[0] if stats and stats[0] else 0
    avg_rating = round(float(stats[1]), 1) if stats and stats[1] else 0
    
    # Обновляем данные в таблице продуктов
    await db.execute(
        select(Product)
        .where(Product.id == product_id)
        .execution_options(synchronize_session="fetch")
        .update(
            {
                "review_count": count,
                "rating": avg_rating
            }
        )
    )
    
    await db.commit()