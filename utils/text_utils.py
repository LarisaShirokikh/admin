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

def clean_text(text: str) -> str:
    """Очищает текст от лишних пробелов и переносов строк"""
    if not text:
        return ""
    # Заменяем множественные пробелы и переносы строк на один пробел
    cleaned = re.sub(r'\s+', ' ', text)
    return cleaned.strip()