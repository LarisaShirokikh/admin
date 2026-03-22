import logging
from typing import Optional
import anthropic
import json

log = logging.getLogger("providers.anthropic")

SEO_PROMPT = """
Ты SEO-копирайтер для интернет-магазина входных дверей в Москве.

Название товара: {product_name}

Характеристики товара:
{attributes}

Сгенерируй два поля:

1. seo_description — связный продающий текст (300-400 слов):
- Естественно вписывай ключи: "входная дверь купить", "стальная дверь", "утеплённая дверь", "дверь с установкой Москва"
- Упоминай конкретные характеристики из списка выше — не придумывай данные
- Структура: преимущества → безопасность → утепление → отделка → доставка

2. meta_description — одна строка до 155 символов:
- Название, ключевое преимущество, призыв к действию
- Пример: "Входная дверь [Название] — сталь 1.8мм, замок KALE, утепление базальтом. Монтаж в Москве за 1 день."

Верни строго JSON без markdown-блоков:
{{"seo_description": "...", "meta_description": "..."}}
"""


def generate_seo_content(
    client: anthropic.Anthropic,
    product_name: str,
    attributes: dict,
) -> Optional[dict]:
    if not attributes:
        log.warning("generate_seo_content: пустые атрибуты для товара %s", product_name)
        return None

    attrs_text = "\n".join(f"- {k}: {v}" for k, v in attributes.items())
    prompt = SEO_PROMPT.format(
        product_name=product_name,
        attributes=attrs_text,
    )

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        return json.loads(raw)

    except json.JSONDecodeError as e:
        log.error("generate_seo_content: ошибка парсинга JSON для %s: %s", product_name, e)
        return None
    except Exception as e:
        log.error("generate_seo_content: ошибка API для %s: %s", product_name, e)
        return None