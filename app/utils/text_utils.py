import hashlib
import re
import time

def generate_slug(text: str) -> str:
    """
    Генерирует slug из текста, гарантируя непустой результат
    на основе исходного текста (без дефолтных значений)
    """
    if not text:
        # Если входной текст пустой, генерируем уникальный хеш
        return f"product-{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}"
    
    # Приводим текст к нижнему регистру перед заменой
    text_lower = text.lower()
    
    # Заменяем кириллицу на латиницу
    translit_map = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'j', 'к': 'k', 'л': 'l', 'м': 'm', 
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 
        'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 
        'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
    }
    
    result = text_lower
    for cyr, lat in translit_map.items():
        result = result.replace(cyr, lat)
    
    # Заменяем все не буквенно-цифровые символы на дефис
    slug = re.sub(r'[^a-z0-9]', '-', result)
    # Удаляем начальные и конечные дефисы
    slug = slug.strip('-')
    # Заменяем повторяющиеся дефисы одним дефисом
    slug = re.sub(r'-+', '-', slug)
    
    # Если после всех операций получили пустой slug,
    # создаем slug на основе ASCII-представления текста
    if not slug:
        # Берем первые 20 символов исходного текста и кодируем их в ASCII,
        # заменяя непечатаемые символы на их коды
        ascii_slug = ''
        for char in text[:20]:
            if ord(char) < 128:  # Если ASCII-символ
                if char.isalnum():  # Если буква или цифра
                    ascii_slug += char.lower()
                else:
                    ascii_slug += '-'
            else:
                # Для не-ASCII символов берем числовой код
                ascii_slug += f"{ord(char)}"
        
        slug = f"p-{ascii_slug}"
        
        # Если и это не помогло, используем хеш оригинального имени
        if not slug or slug == "p-":
            slug = f"p-{hashlib.md5(text.encode()).hexdigest()[:12]}"
    
    return slug

def generate_seo_meta(name: str) -> dict:
    """Автоматическая генерация SEO мета-тегов"""
    
    # Определяем тип товара для более точных мета-тегов
    name_lower = name.lower()
    
    # Ключевые слова в зависимости от категории
    keywords_map = {
        'двер': ['двери', 'дверь', 'входные', 'металлические'],
        'фурнитур': ['фурнитура', 'ручки', 'замки', 'петли', 'аксессуары'],
        'стекл': ['стекло', 'витражи', 'зеркала', 'стеклянные'],
    }
    
    # Найдем подходящие ключевые слова
    category_keywords = []
    for key, words in keywords_map.items():
        if key in name_lower:
            category_keywords.extend(words)
            break
    
    # Если не нашли специфичные, используем общие
    if not category_keywords:
        category_keywords = ['товары', 'продукция', 'каталог']
    
    # Генерируем мета-теги
    meta_title = f"{name} - купить в интернет-магазине | Лучшие цены"
    
    meta_description = f"Купить {name.lower()} в нашем интернет-магазине. " \
                      f"Широкий выбор, лучшие цены, быстрая доставка. " \
                      f"Гарантия качества на все товары категории {name}."
    
    # Ограничиваем длину описания (для SEO оптимально до 160 символов)
    if len(meta_description) > 160:
        meta_description = f"Купить {name.lower()} - широкий выбор, лучшие цены, быстрая доставка. Гарантия качества."
    
    # Генерируем ключевые слова
    meta_keywords = f"{name.lower()}, {', '.join(category_keywords[:5])}, купить, цена, интернет-магазин"
    
    return {
        "meta_title": meta_title,
        "meta_description": meta_description,
        "meta_keywords": meta_keywords
    }

def clean_text(text: str) -> str:
    """Очищает текст от лишних пробелов и переносов строк"""
    if not text:
        return ""
    # Заменяем множественные пробелы и переносы строк на один пробел
    cleaned = re.sub(r'\s+', ' ', text)
    return cleaned.strip()