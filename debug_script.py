import requests
from bs4 import BeautifulSoup
import os

# Установка уровня логирования
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("test_intecron")

def save_html(content, filename):
    """Сохраняет HTML в файл"""
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    logger.info(f"Файл сохранен: {filename}")

def test_intecron_parser():
    """Тестирует парсинг сайта Intecron"""
    url = "https://intecron-msk.ru/catalog/intekron/gektor/"
    
    # Пробуем разные User-Agent
    headers_list = [
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
        },
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        }
    ]
    
    for i, headers in enumerate(headers_list):
        logger.info(f"Тест #{i+1} с User-Agent: {headers['User-Agent'][:30]}...")
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            # Сохраняем полученный HTML
            save_html(response.text, f"test_intecron_{i+1}.html")
            
            # Парсим HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Выводим заголовок страницы
            title = soup.title.string if soup.title else "Нет заголовка"
            logger.info(f"Заголовок страницы: {title}")
            
            # Проверяем наличие защиты от ботов
            if "captcha" in response.text.lower() or "robot" in response.text.lower():
                logger.warning("Обнаружена возможная защита от ботов!")
            
            # Ищем товары разными способами
            selectors = [
                ".catalog2-row .pr-bl",
                ".pr-bl",
                "div[class*='pr-bl']",
                ".catalog2-row .col",
                ".catalog2-row.fl-row .col",
                ".fl-row .col"
            ]
            
            for selector in selectors:
                items = soup.select(selector)
                logger.info(f"Селектор '{selector}': {len(items)} элементов")
                
                # Если нашли элементы, проверяем первый
                if items:
                    # Проверяем наличие изображения
                    img = items[0].select_one("img")
                    if img:
                        logger.info(f"Изображение: {img.get('src', '')[:50]}")
                    
                    # Проверяем наличие имени
                    name_elem = items[0].select_one("h4") or items[0].select_one(".h4") or items[0].select_one(".name")
                    if name_elem:
                        logger.info(f"Название: {name_elem.text.strip()}")
                    
                    # Проверяем наличие цены
                    price_elem = items[0].select_one(".price")
                    if price_elem:
                        logger.info(f"Цена: {price_elem.text.strip()}")
                    
                    # Проверяем наличие ссылки
                    links = items[0].find_all("a", href=True)
                    if links:
                        logger.info(f"Ссылка: {links[0]['href']}")
            
            # Получаем все классы на странице
            all_classes = set()
            for tag in soup.find_all(class_=True):
                for cls in tag.get('class', []):
                    all_classes.add(cls)
            
            logger.info(f"Всего найдено {len(all_classes)} уникальных классов")
            logger.info(f"Примеры классов: {', '.join(list(all_classes)[:10])}")
            
            # Ищем все ссылки на товары
            product_links = []
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                if '/product/' in href or ('/catalog/' in href and href.count('/') > 2):
                    product_links.append(href)
            
            logger.info(f"Найдено {len(product_links)} ссылок на товары")
            
        except Exception as e:
            logger.error(f"Ошибка при тестировании: {e}")

if __name__ == "__main__":
    test_intecron_parser()