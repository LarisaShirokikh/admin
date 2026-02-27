# app/crud/product_ranking.py
import logging
import uuid
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.analytics import AnalyticsDailySummary, AnalyticsEvent, AnalyticsSession
from app.models.product_ranking import ProductRanking as ProductRankingModel

logger = logging.getLogger(__name__)

class ProductRanking:
    """Сервис для управления ранжированием товаров и аналитикой"""
    
    @staticmethod
    async def process_product_view(
        db: AsyncSession, 
        product_id: Any, 
        session_data: Dict[str, Any] = None
    ) -> None:
        """
        Обрабатывает просмотр продукта
        """
        logger.info(f"🔍 ProductRanking.process_product_view: Начало обработки продукта {product_id}")
        logger.info(f"📋 Данные сессии: {session_data}")
        
        try:
            session_data = session_data or {}
            
            # 1. Сохраняем событие в аналитику
            logger.info("💾 Сохраняем событие аналитики...")
            await ProductRanking._save_analytics_event(
                db=db,
                product_id=product_id,
                event_type='view',
                event_subtype='product_page',
                event_data={},
                session_data=session_data
            )
            logger.info("✅ Событие аналитики сохранено")
            
            # 2. Обновляем/создаем сессию
            logger.info("👤 Обновляем сессию...")
            session_id = ProductRanking._get_or_generate_session_id(session_data)
            await ProductRanking._update_session(db, session_id, session_data, 'product_view')
            logger.info("✅ Сессия обновлена")
            
            # 3. Обновляем рейтинг продукта
            logger.info("⭐ Обновляем рейтинг продукта...")
            await ProductRanking._update_product_ranking(db, product_id, 'view')
            logger.info("✅ Рейтинг продукта обновлен")
            
            # 4. Обновляем дневную статистику
            logger.info("📈 Обновляем дневную статистику...")
            await ProductRanking._update_daily_summary(db, product_id, 'view')
            logger.info("✅ Дневная статистика обновлена")
            
            # 5. Коммитим изменения
            logger.info("💾 Коммитим изменения в БД...")
            await db.commit()
            logger.info(f"✅ Просмотр продукта {product_id} успешно обработан и сохранен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке просмотра продукта {product_id}: {str(e)}")
            logger.error(f"❌ Тип ошибки: {type(e).__name__}")
            import traceback
            logger.error(f"❌ Stacktrace: {traceback.format_exc()}")
            await db.rollback()
            raise

    @staticmethod
    async def process_product_interaction(
        db: AsyncSession,
        product_id: Any,
        interaction_type: str,
        interaction_data: Dict[str, Any] = None,
        session_data: Dict[str, Any] = None
    ) -> None:
        """
        Обрабатывает взаимодействие с продуктом
        """
        logger.info(f"🔍 ProductRanking.process_product_interaction: продукт {product_id}, тип {interaction_type}")
        logger.info(f"📋 Данные взаимодействия: {interaction_data}")
        logger.info(f"📋 Данные сессии: {session_data}")
        
        try:
            session_data = session_data or {}
            interaction_data = interaction_data or {}
            
            # 1. Сохраняем событие в аналитику
            logger.info("💾 Сохраняем взаимодействие в аналитику...")
            await ProductRanking._save_analytics_event(
                db=db,
                product_id=product_id,
                event_type='interaction',
                event_subtype=interaction_type,
                event_data=interaction_data,
                session_data=session_data
            )
            logger.info("✅ Взаимодействие сохранено")
            
            # 2. Обновляем сессию
            logger.info("👤 Обновляем сессию...")
            session_id = ProductRanking._get_or_generate_session_id(session_data)
            await ProductRanking._update_session(db, session_id, session_data, 'interaction')
            logger.info("✅ Сессия обновлена")
            
            # 3. Обновляем рейтинг продукта
            logger.info("⭐ Обновляем рейтинг продукта...")
            await ProductRanking._update_product_ranking(db, product_id, 'interaction', interaction_type, interaction_data)
            logger.info("✅ Рейтинг продукта обновлен")
            
            # 4. Обновляем дневную статистику
            logger.info("📈 Обновляем дневную статистику...")
            await ProductRanking._update_daily_summary(db, product_id, 'interaction')
            logger.info("✅ Дневная статистика обновлена")
            
            # 5. Коммитим изменения
            logger.info("💾 Коммитим изменения в БД...")
            await db.commit()
            logger.info(f"✅ Взаимодействие '{interaction_type}' для продукта {product_id} успешно обработано")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке взаимодействия '{interaction_type}' для продукта {product_id}: {str(e)}")
            logger.error(f"❌ Тип ошибки: {type(e).__name__}")
            import traceback
            logger.error(f"❌ Stacktrace: {traceback.format_exc()}")
            await db.rollback()
            raise

    @staticmethod
    async def _save_analytics_event(
        db: AsyncSession,
        product_id: int,
        event_type: str,
        event_subtype: str = None,
        event_data: Dict[str, Any] = None,
        session_data: Dict[str, Any] = None
    ) -> None:
        """
        Сохраняет событие аналитики в БД
        """
        logger.info(f"💾 _save_analytics_event: {event_type}/{event_subtype} для продукта {product_id}")
        
        session_data = session_data or {}
        event_data = event_data or {}
        
        # Извлекаем данные сессии
        session_id = ProductRanking._get_or_generate_session_id(session_data)
        user_agent = session_data.get('user_agent', '')
        device_type = session_data.get('device_type', 'unknown')
        referrer = session_data.get('referrer', '')
        page_url = session_data.get('url', '')
        ip_address = session_data.get('ip_address', '')  # Добавляем IP адрес
        
        logger.info(f"🔧 Создаем объект AnalyticsEvent:")
        logger.info(f"   - product_id: {product_id}")
        logger.info(f"   - session_id: {session_id}")
        logger.info(f"   - user_agent: {user_agent[:50]}...")  # Показываем первые 50 символов
        logger.info(f"   - device_type: {device_type}")
        logger.info(f"   - page_url: {page_url}")
        logger.info(f"   - ip_address: {ip_address}")
        logger.info(f"   - referrer: {referrer}")
        
        try:
            event = AnalyticsEvent(
                product_id=product_id,
                event_type=event_type,
                event_subtype=event_subtype,
                event_data=event_data,
                session_id=session_id,
                user_agent=user_agent,
                device_type=device_type,
                referrer=referrer,
                page_url=page_url,
                ip_address=ip_address,  # Добавляем IP адрес
            )
            
            logger.info("➕ Добавляем событие в сессию БД...")
            db.add(event)
            
            logger.info("💾 Выполняем flush...")
            await db.flush()
            
            logger.info(f"✅ Событие успешно сохранено с ID: {event.id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при создании/сохранении AnalyticsEvent: {str(e)}")
            import traceback
            logger.error(f"❌ Stacktrace: {traceback.format_exc()}")
            raise
    @staticmethod
    async def _update_session(
        db: AsyncSession,
        session_id: str,
        session_data: Dict[str, Any],
        action_type: str
    ) -> None:
        """
        Обновляет или создает сессию пользователя
        """
        logger.info(f"👤 _update_session: {session_id}, тип: {action_type}")
        
        try:
            # Ищем существующую сессию
            logger.info("🔍 Ищем существующую сессию...")
            query = select(AnalyticsSession).where(AnalyticsSession.session_id == session_id)
            result = await db.execute(query)
            session = result.scalar_one_or_none()
            
            if not session:
                logger.info("➕ Создаем новую сессию...")
                # Создаем новую сессию
                session = AnalyticsSession(
                    session_id=session_id,
                    user_agent=session_data.get('user_agent', ''),
                    device_type=session_data.get('device_type', 'unknown'),
                    first_page=session_data.get('url', ''),
                    referrer=session_data.get('referrer', ''),
                )
                db.add(session)
                logger.info(f"✅ Новая сессия создана: {session_id}")
            else:
                logger.info(f"📝 Обновляем существующую сессию: {session_id}")
            
            # Обновляем данные сессии
            session.last_page = session_data.get('url', session.last_page)
            session.last_activity = datetime.utcnow()
            
            if action_type == 'product_view':
                session.page_views = (session.page_views or 0) + 1
                session.products_viewed = (session.products_viewed or 0) + 1
                logger.info(f"📊 Счетчики: page_views={session.page_views}, products_viewed={session.products_viewed}")
            elif action_type == 'interaction':
                session.interactions_count = (session.interactions_count or 0) + 1
                logger.info(f"📊 Счетчик взаимодействий: {session.interactions_count}")
            
            # Вычисляем длительность сессии
            if session.started_at:
                session.duration_seconds = int((session.last_activity - session.started_at).total_seconds())
                logger.info(f"⏱️ Длительность сессии: {session.duration_seconds} секунд")
            
            logger.info("✅ Сессия успешно обновлена")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении сессии {session_id}: {str(e)}")
            import traceback
            logger.error(f"❌ Stacktrace: {traceback.format_exc()}")
            raise

    @staticmethod
    async def _update_daily_summary(
        db: AsyncSession,
        product_id: int,
        action_type: str,
        duration_seconds: int = 0
    ) -> None:
        """
        Обновляет дневную агрегированную статистику
        """
        logger.info(f"📈 _update_daily_summary: продукт {product_id}, тип {action_type}")
        
        try:
            today = date.today()
            logger.info(f"📅 Сегодняшняя дата: {today}")
            
            # Ищем запись за сегодня
            logger.info("🔍 Ищем запись дневной статистики...")
            query = select(AnalyticsDailySummary).where(
                AnalyticsDailySummary.product_id == product_id,
                func.date(AnalyticsDailySummary.date) == today
            )
            result = await db.execute(query)
            summary = result.scalar_one_or_none()
            
            if not summary:
                logger.info("➕ Создаем новую запись дневной статистики...")
                # Создаем новую запись
                summary = AnalyticsDailySummary(
                    product_id=product_id,
                    date=datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                )
                db.add(summary)
                logger.info(f"✅ Новая дневная статистика создана для продукта {product_id}")
            else:
                logger.info(f"📝 Обновляем существующую дневную статистику для продукта {product_id}")
            
            # Обновляем счетчики
            if action_type == 'view':
                old_views = summary.views_count or 0
                summary.views_count = old_views + 1
                logger.info(f"👁️ Счетчик просмотров: {old_views} -> {summary.views_count}")
            elif action_type == 'interaction':
                old_interactions = summary.interactions_count or 0
                summary.interactions_count = old_interactions + 1
                logger.info(f"🤝 Счетчик взаимодействий: {old_interactions} -> {summary.interactions_count}")
            
            if duration_seconds > 0:
                old_duration = summary.total_view_duration or 0
                summary.total_view_duration = old_duration + duration_seconds
                logger.info(f"⏱️ Общее время просмотра: {old_duration} -> {summary.total_view_duration}")
                
                # Пересчитываем среднее время просмотра
                if summary.views_count > 0:
                    summary.avg_view_duration = summary.total_view_duration // summary.views_count
                    logger.info(f"📊 Среднее время просмотра: {summary.avg_view_duration}")
            
            summary.updated_at = datetime.utcnow()
            logger.info("✅ Дневная статистика успешно обновлена")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении дневной статистики для продукта {product_id}: {str(e)}")
            import traceback
            logger.error(f"❌ Stacktrace: {traceback.format_exc()}")
            raise

    @staticmethod
    def _get_or_generate_session_id(session_data: Dict[str, Any]) -> str:
        """
        Получает session_id из данных или генерирует новый
        """
        session_id = session_data.get('session_id')
        if not session_id:
            session_id = str(uuid.uuid4())
            logger.info(f"🆔 Сгенерирован новый session_id: {session_id}")
        else:
            logger.info(f"🆔 Используем существующий session_id: {session_id}")
        return session_id

    @staticmethod
    async def _update_product_ranking(
        db: AsyncSession,
        product_id: int,
        action_type: str,
        interaction_type: str = None,
        interaction_data: Dict[str, Any] = None
    ) -> None:
        """
        Обновляет рейтинг продукта
        """
        logger.info(f"⭐ _update_product_ranking: продукт {product_id}, тип {action_type}")
        
        try:
            ranking_query = select(ProductRankingModel).where(ProductRankingModel.product_id == product_id)
            result = await db.execute(ranking_query)
            ranking = result.scalar_one_or_none()
            
            if not ranking:
                logger.info("➕ Создаем новую запись рейтинга...")
                ranking = ProductRankingModel(product_id=product_id)
                db.add(ranking)
                await db.flush()
                logger.info(f"✅ Новая запись рейтинга создана для продукта {product_id}")
            else:
                logger.info(f"📝 Обновляем существующий рейтинг для продукта {product_id}")
            
            old_score = ranking.ranking_score or 0
            old_impressions = ranking.impressions_count or 0
            
            if action_type == 'view':
                ranking.impressions_count = old_impressions + 1
                ranking.ranking_score = min(100, old_score + 0.1)
                logger.info(f"👁️ Просмотр: impressions {old_impressions} -> {ranking.impressions_count}")
                logger.info(f"⭐ Рейтинг: {old_score} -> {ranking.ranking_score}")
            
            elif action_type == 'interaction':
                interaction_weights = {
                    "view_image": 0.2,
                    "view_duration": 0.5,
                    "contact": 1.5,
                    "default": 0.2
                }
                weight = interaction_weights.get(interaction_type, interaction_weights["default"])
                ranking.ranking_score = min(100, old_score + weight)
                logger.info(f"🤝 Взаимодействие '{interaction_type}': рейтинг {old_score} -> {ranking.ranking_score} (+{weight})")
            
            ranking.updated_at = datetime.utcnow()
            logger.info("✅ Рейтинг продукта успешно обновлен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении рейтинга продукта {product_id}: {str(e)}")
            import traceback
            logger.error(f"❌ Stacktrace: {traceback.format_exc()}")
            raise

    @staticmethod
    async def process_analytics_events(db: AsyncSession, events: List[Dict[str, Any]]) -> None:
        """
        Обрабатывает список событий аналитики с клиента
        """
        logger.info(f"📦 Обрабатываем пакет из {len(events)} событий")
        try:
            for event in events:
                logger.info(f"📋 Обрабатываем событие: {event}")
                # Здесь можно добавить логику обработки пакетных событий
            logger.info("✅ Пакет событий обработан")
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке пакета событий: {str(e)}")
            raise