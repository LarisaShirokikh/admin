# app/services/product_ranking_service.py (в админ-бэкенде)
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy import func, select, update, desc, case, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.product import Product
from app.models.product_ranking import ProductRanking
from app.models.category import Category

logger = logging.getLogger(__name__)

class ProductRankingService:
    """Сервис для управления ранжированием товаров"""
    
    @staticmethod
    async def ensure_ranking_records(db: AsyncSession) -> None:
        """
        Убеждается, что для каждого товара есть запись ранжирования
        """
        try:
            # Получаем все ID товаров
            products_query = select(Product.id)
            products_result = await db.execute(products_query)
            product_ids = [row[0] for row in products_result.all()]
            
            # Получаем ID товаров, для которых уже есть записи ранжирования
            existing_rankings_query = select(ProductRanking.product_id)
            existing_result = await db.execute(existing_rankings_query)
            existing_product_ids = [row[0] for row in existing_result.all()]
            
            # Находим товары без записей ранжирования
            missing_product_ids = set(product_ids) - set(existing_product_ids)
            
            # Создаем записи ранжирования для отсутствующих товаров
            for product_id in missing_product_ids:
                ranking = ProductRanking(product_id=product_id)
                db.add(ranking)
            
            await db.commit()
            if missing_product_ids:
                logger.info(f"Создано {len(missing_product_ids)} записей ранжирования для новых товаров")
                
        except Exception as e:
            logger.error(f"Ошибка при создании записей ранжирования: {str(e)}")
            await db.rollback()
    
    @staticmethod
    async def update_admin_settings(
        db: AsyncSession,
        product_id: int,
        admin_score: Optional[float] = None,
        is_featured: Optional[bool] = None,
        priority_days: Optional[int] = None,
        seasonal_relevance: Optional[Dict[str, int]] = None,
        category_boost: Optional[float] = None,
        custom_tags: Optional[Dict] = None
    ) -> None:
        """
        Обновляет административные настройки ранжирования товара
        """
        try:
            # Проверяем, существует ли запись ранжирования для этого товара
            ranking_query = select(ProductRanking).where(ProductRanking.product_id == product_id)
            result = await db.execute(ranking_query)
            ranking = result.scalar_one_or_none()
            
            if not ranking:
                # Создаем новую запись, если не существует
                ranking = ProductRanking(product_id=product_id)
                db.add(ranking)
                await db.flush()
            
            # Обновляем только указанные поля
            update_values = {}
            
            if admin_score is not None:
                update_values["admin_score"] = max(0, min(admin_score, 100))  # Ограничиваем 0-100
                
            if is_featured is not None:
                update_values["is_featured"] = is_featured
                
            if priority_days is not None:
                if priority_days > 0:
                    update_values["priority_until"] = datetime.utcnow() + timedelta(days=priority_days)
                else:
                    update_values["priority_until"] = None
                    
            if seasonal_relevance is not None:
                # Проверяем, что значения в диапазоне 0-100
                valid_seasons = {}
                for season, value in seasonal_relevance.items():
                    if season in ["winter", "spring", "summer", "autumn"]:
                        valid_seasons[season] = max(0, min(value, 100))
                update_values["seasonal_relevance"] = valid_seasons
                
            if category_boost is not None:
                update_values["category_boost"] = max(0, min(category_boost, 5))  # Ограничиваем 0-5
                
            if custom_tags is not None:
                update_values["custom_tags"] = custom_tags
            
            # Применяем обновления
            if update_values:
                for key, value in update_values.items():
                    setattr(ranking, key, value)
                
                ranking.updated_at = datetime.utcnow()
                await db.commit()
                
                # Запускаем пересчет рейтинга для этого товара
                await ProductRankingService.recalculate_ranking(db, product_id)
                
                logger.info(f"Обновлены настройки ранжирования для товара {product_id}")
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении настроек ранжирования товара {product_id}: {str(e)}")
            await db.rollback()
    
    @staticmethod
    async def update_impressions_count(
        db: AsyncSession,
        product_id: int,
        additional_impressions: int = 1
    ) -> None:
        """
        Обновляет счетчик показов товара (может вызываться периодически на основе данных GA)
        """
        try:
            await db.execute(
                update(ProductRanking)
                .where(ProductRanking.product_id == product_id)
                .values(
                    impressions_count=ProductRanking.impressions_count + additional_impressions,
                    updated_at=func.now()
                )
            )
            await db.commit()
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении счетчика показов товара {product_id}: {str(e)}")
            await db.rollback()
    
    @staticmethod
    async def recalculate_ranking(
        db: AsyncSession, 
        product_id: Optional[int] = None
    ) -> None:
        """
        Пересчитывает рейтинг для одного или всех товаров
        """
        try:
            # Если указан конкретный product_id, пересчитываем только для него
            if product_id:
                await ProductRankingService._recalculate_single_product_ranking(db, product_id)
            else:
                # Убеждаемся, что для всех товаров есть записи ранжирования
                await ProductRankingService.ensure_ranking_records(db)
                
                # Получаем все товары с их настройками ранжирования
                query = select(
                    Product, 
                    ProductRanking
                ).outerjoin(
                    ProductRanking, 
                    Product.id == ProductRanking.product_id
                ).where(
                    Product.is_active == True
                )
                
                result = await db.execute(query)
                products_with_rankings = result.all()
                
                # Пересчитываем рейтинг для каждого товара
                for product, ranking in products_with_rankings:
                    # Если записи ранжирования нет, создаем ее
                    if not ranking:
                        ranking = ProductRanking(product_id=product.id)
                        db.add(ranking)
                        await db.flush()
                    
                    # Рассчитываем новый рейтинг
                    ranking_score = await ProductRankingService._calculate_product_ranking(
                        db, product, ranking
                    )
                    
                    # Обновляем рейтинг
                    ranking.ranking_score = ranking_score
                    ranking.last_recalculated = datetime.utcnow()
                
                await db.commit()
                logger.info(f"Пересчитаны рейтинги для {len(products_with_rankings)} товаров")
                
        except Exception as e:
            logger.error(f"Ошибка при пересчете рейтингов товаров: {str(e)}")
            await db.rollback()
    
    @staticmethod
    async def _recalculate_single_product_ranking(db: AsyncSession, product_id: int) -> None:
        """
        Пересчитывает рейтинг для одного товара
        """
        try:
            # Получаем товар и его настройки ранжирования
            query = select(
                Product, 
                ProductRanking
            ).outerjoin(
                ProductRanking, 
                Product.id == ProductRanking.product_id
            ).where(
                Product.id == product_id,
                Product.is_active == True
            )
            
            result = await db.execute(query)
            product_with_ranking = result.first()
            
            if not product_with_ranking:
                logger.warning(f"Товар {product_id} не найден или не активен")
                return
            
            product, ranking = product_with_ranking
            
            # Если записи ранжирования нет, создаем ее
            if not ranking:
                ranking = ProductRanking(product_id=product_id)
                db.add(ranking)
                await db.flush()
            
            # Рассчитываем новый рейтинг
            ranking_score = await ProductRankingService._calculate_product_ranking(
                db, product, ranking
            )
            
            # Обновляем рейтинг
            ranking.ranking_score = ranking_score
            ranking.last_recalculated = datetime.utcnow()
            
            await db.commit()
            logger.info(f"Пересчитан рейтинг для товара {product_id}: {ranking_score}")
            
        except Exception as e:
            logger.error(f"Ошибка при пересчете рейтинга товара {product_id}: {str(e)}")
            await db.rollback()
    
    @staticmethod
    async def _calculate_product_ranking(
        db: AsyncSession, 
        product: Product, 
        ranking: ProductRanking
    ) -> float:
        """
        Рассчитывает рейтинг для товара на основе всех доступных метрик
        """
        # Базовый рейтинг (может быть уже установлен в поле popularity_score)
        base_score = product.popularity_score or 0
        
        # 1. Учитываем административные настройки (40% от общего веса)
        admin_component = 0
        
        # Admin score (0-100)
        admin_component += ranking.admin_score * 0.5  # 50% от адм. компонента
        
        # Featured bonus (0 или 20)
        if ranking.is_featured:
            admin_component += 20 * 0.3  # 30% от адм. компонента
        
        # Priority bonus (0-15)
        if ranking.priority_until and ranking.priority_until > datetime.utcnow():
            days_left = (ranking.priority_until - datetime.utcnow()).days
            priority_bonus = min(days_left, 30) / 30 * 15  # До 15 баллов за месяц приоритета
            admin_component += priority_bonus * 0.2  # 20% от адм. компонента
        
        # 2. Учитываем характеристики товара (40% от общего веса)
        product_component = 0
        
        # In stock bonus (0 или 10)
        if product.in_stock:
            product_component += 10 * 0.2  # 20% от товарного компонента
        
        # Newness bonus (0-25)
        if product.created_at:
            days_since_creation = (datetime.utcnow() - product.created_at).days
            if days_since_creation < 90:  # Если товар добавлен менее 3 месяцев назад
                newness_bonus = (90 - days_since_creation) / 90 * 25  # До 25 баллов для самых новых
                product_component += newness_bonus * 0.3  # 30% от товарного компонента
        
        # Discount bonus (0-20)
        if product.discount_price and product.price:
            discount_percent = (product.price - product.discount_price) / product.price * 100
            if discount_percent > 0:
                discount_bonus = min(discount_percent, 50) / 50 * 20  # До 20 баллов для скидок 50% и выше
                product_component += discount_bonus * 0.3  # 30% от товарного компонента
        
        # Type multiplier (если есть в модели Product)
        if hasattr(product, 'type') and product.type and ranking.product_type_multiplier:
            product_component *= ranking.product_type_multiplier
            
        # Price range multiplier
        if product.price and ranking.price_range_multiplier:
            product_component *= ranking.price_range_multiplier
        
        # 3. Учитываем сезонность (20% от общего веса)
        seasonal_component = 0
        
        if ranking.seasonal_relevance:
            # Определяем текущий сезон
            now = datetime.timezone.utc()
            month = now.month
            season = "winter"
            if 3 <= month <= 5:
                season = "spring"
            elif 6 <= month <= 8:
                season = "summer"
            elif 9 <= month <= 11:
                season = "autumn"
                
            if season in ranking.seasonal_relevance:
                seasonal_component = ranking.seasonal_relevance[season]
        
        # Составляем итоговый рейтинг из компонентов
        ranking_score = (
            base_score * 0.1 +  # 10% - базовый скор из модели
            admin_component * 0.4 +  # 40% - административный компонент
            product_component * 0.3 +  # 30% - товарный компонент
            seasonal_component * 0.2   # 20% - сезонный компонент
        )
        
        # Применяем множитель категории, если указан
        if ranking.category_boost:
            ranking_score *= (1 + (ranking.category_boost / 10))  # Например, 1.5 = +50% к рейтингу
        
        # Ограничиваем рейтинг диапазоном 0-100
        return max(0, min(ranking_score, 100))