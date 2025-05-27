from sqlalchemy import func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.product import Product
from app.models.catalog import Catalog
from app.models.category import Category
from typing import Optional, List, Dict, Tuple
import re
import logging
logger = logging.getLogger(__name__)

async def detect_product_for_video(
    db: AsyncSession, 
    title: str, 
    description: Optional[str] = None
) -> Optional[Product]:
    """
    Улучшенная функция для более точного определения продукта на основе заголовка и описания видео.
    """
    if not title:
        return None
    
    # Нормализация текста
    search_text = title.lower()
    if description:
        search_text += " " + description.lower()
    
    # Очистка текста от спецсимволов и удаление стоп-слов
    search_text = re.sub(r'[^\w\s]', ' ', search_text)
    stop_words = {'и', 'в', 'на', 'с', 'по', 'для', 'от', 'к', 'о', 'из', 'у', 'за', 'как', 'обзор', 'видео'}
    words = [word for word in search_text.split() if word not in stop_words and len(word) > 2]
    
    if not words:
        return None
    
    # Найдем все продукты с точным соответствием в названии
    exact_match_query = select(Product).where(
        func.lower(Product.name).contains(" ".join(words[:2]))
    )
    
    result = await db.execute(exact_match_query)
    exact_match = result.scalars().first()
    
    if exact_match:
        return exact_match
    
    # Поиск по отдельным словам с весами
    word_conditions = []
    for word in words:
        if len(word) > 3:  # Игнорируем короткие слова для уменьшения шума
            word_conditions.append(func.lower(Product.name).contains(word))
            if description:
                word_conditions.append(func.lower(Product.description).contains(word))
    
    if not word_conditions:
        return None
    
    # Собираем все продукты с совпадениями для подсчета релевантности
    query = select(Product).where(or_(*word_conditions))
    result = await db.execute(query)
    products = result.scalars().all()
    
    if not products:
        return None
    
    # Подсчет релевантности для каждого продукта
    relevance_scores = {}
    for product in products:
        score = 0
        product_name_lower = product.name.lower()
        product_description_lower = product.description.lower() if product.description else ""
        
        # Проверка на совпадение модели или артикула (важные слова)
        model_pattern = r'[а-яА-Я0-9]+-\d+'
        models_in_search = re.findall(model_pattern, search_text)
        models_in_product = re.findall(model_pattern, product_name_lower)
        
        # Если найдено совпадение по модели/артикулу - высокий приоритет
        if models_in_search and models_in_product:
            if any(m in product_name_lower for m in models_in_search):
                score += 100
        
        # Проверка на совпадение по названию
        for word in words:
            if word in product_name_lower:
                # Слова в названии имеют больший вес
                score += 10
            elif product_description_lower and word in product_description_lower:
                # Слова в описании имеют меньший вес
                score += 3
        
        # Бонус за длину названия - чем короче, тем лучше (более конкретное)
        name_length_bonus = max(0, 50 - len(product_name_lower)) / 5
        score += name_length_bonus
        
        relevance_scores[product.id] = score
    
    # Выбираем продукт с максимальной релевантностью
    if relevance_scores:
        best_product_id = max(relevance_scores, key=relevance_scores.get)
        best_product = next((p for p in products if p.id == best_product_id), None)
        logger.warning(
            f"Низкая релевантность ({relevance_scores[best_product_id]}) "
            f"для видео '{title}' и продукта {best_product.name}"
        )
        
        # Проверка порога релевантности
        if best_product and relevance_scores[best_product_id] > 10:
            logger.info(
                f"Для видео '{title}' найден продукт: {best_product.name} "
                f"(релевантность: {relevance_scores[best_product_id]})"
            )
            return best_product
    
    return None