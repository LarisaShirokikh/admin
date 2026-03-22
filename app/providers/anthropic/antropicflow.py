import json
import logging
from typing import Optional
import anthropic

from app.providers.anthropic.ansession import create_anthropic_client
from app.providers.anthropic.antropicapi import generate_seo_content

log = logging.getLogger("providers.anthropic")


def generate_product_seo(
    product_name: str,
    attributes: dict,
) -> Optional[dict]:
    client = create_anthropic_client()
    if not client:
        return None

    result = generate_seo_content(client, product_name, attributes)
    if result:
        log.info("SEO сгенерировано для товара: %s", product_name)
    return result


def classify_product_categories(
    client: anthropic.Anthropic,
    product_name: str,
    attributes: dict,
    categories: list[str],  # список названий категорий
) -> list[str]:
    """Возвращает список категорий подходящих для товара."""
    if not categories:
        return []

    attrs_text = "\n".join(f"- {k}: {v}" for k, v in (attributes or {}).items())
    cats_text = "\n".join(f"- {c}" for c in categories)

    prompt = f"""Ты помогаешь классифицировать входные двери по категориям интернет-магазина.

Товар: {product_name}
Характеристики:
{attrs_text}

Доступные категории:
{cats_text}

Выбери ТОЛЬКО те категории, которым соответствует этот товар.
Правила:
- Категории цвета (белые, черные, серые и т.д.) назначай строго по цвету внешней отделки
- Не добавляй категорию если нет явного подтверждения в названии или характеристиках
- Категорию "Все двери" всегда включай
- для категории "двери для квартиры" добавляй все двери, если нет в характеристиках или описания терморазрыв....
- для категории "двери в дом" добавляй все двери, если есть упоминание терморазрыв
- Категория "лофт...." - это серая внешняя отделка
- "Венге" - это коричневая внешняя отделка

Ответь ТОЛЬКО валидным JSON массивом строк — названиями подходящих категорий. Без пояснений.
Пример: ["Все двери", "Белые двери", "Металлические снаружи"]"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        result = json.loads(raw)
        if isinstance(result, list):
            return [r for r in result if r in categories]
        return []
    except Exception as e:
        log.error("classify_product_categories: ошибка для %s: %s", product_name, e)
        return []