import logging
from typing import Optional
import anthropic
from app.core.config import settings

log = logging.getLogger("providers.anthropic")


def create_anthropic_client() -> Optional[anthropic.Anthropic]:
    if not settings.ANTHROPIC_ENABLED:
        log.info("Anthropic provider is disabled")
        return None
    if not settings.ANTHROPIC_API_KEY:
        log.error("ANTHROPIC_API_KEY is not configured")
        return None
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)