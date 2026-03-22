import logging
from typing import Optional

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