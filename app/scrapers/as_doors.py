"""Scraper for the AS Doors site as-doors.ru ("Ателье стальных дверей").

Rewritten 2026-07-10 for the current BaseScraper architecture (diff-sync,
content_hash, category_rules).

Donor specifics:
- Anti-bot: the site sets a cookie via a redirect chain (sph_support_check);
  plain requests.get follows it fine within a single call.
- The only real product section is /onstock/ ("Складская программа"):
  a flat grid of ~270 doors, each card carries name, price and photo —
  everything needed, so product pages are not fetched at all.
- No spec tables on the donor side → attributes stay empty, categories are
  assigned by name-based rules.
Shop catalog = single "АС Двери (в наличии)", product = a stock door.
"""
import logging
import re
from typing import Dict, List

from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession

from app.scrapers.base_scraper import BaseScraper
from app.utils.text_utils import generate_slug, clean_text

logger = logging.getLogger("as_doors_scraper")

_ONSTOCK_URL = "https://as-doors.ru/onstock/"
# Must equal the URL tail: deactivate_missing_catalogs compares catalog slugs
# against discover_catalogs URL tails.
_CATALOG_SLUG = "onstock"
_CATALOG_NAME = "АС Двери (в наличии)"


def clean_product_name(raw: str) -> str:
    """'Стальная дверь "Лидер"' → 'Входная дверь АС Лидер'."""
    name = raw or ""
    name = re.sub(r"[«»\"“”]", "", name)
    name = re.sub(r"стальн(ая|ые)\s+двер(ь|и)\s*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"входн(ая|ые)\s+двер(ь|и)\s*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+", " ", name).strip(" -—.,")
    return f"Входная дверь АС {name}".strip() if name else "Входная дверь АС"


class AsDoorsScraper(BaseScraper):
    def __init__(self):
        super().__init__(
            brand_name="АС Двери",
            brand_slug="as-doors",
            base_url="https://as-doors.ru",
            logger_name="as_doors_scraper",
        )

    def discover_catalogs(self, main_url: str) -> List[Dict[str, str]]:
        return [{"url": _ONSTOCK_URL, "name": _CATALOG_NAME}]

    async def parse_catalog(
        self,
        catalog_url: str,
        db: AsyncSession,
        brand_id: int,
        catalog_name: str = "",
    ) -> List[Dict]:
        html = self.get_html(_ONSTOCK_URL)
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")

        catalog = await self.ensure_catalog(
            db, catalog_name or _CATALOG_NAME, _CATALOG_SLUG, brand_id
        )
        catalog_id = catalog.id

        items = soup.select("div.instock_item")
        self.logger.info("Onstock grid has %d cards", len(items))

        products: List[Dict] = []
        first_image_url = None
        for item in items:
            try:
                parsed = self._parse_card(item, catalog_id, brand_id)
                if parsed:
                    products.append(parsed)
                    if not first_image_url and parsed["image_urls"]:
                        candidate = parsed["image_urls"][0]
                        if len(candidate) <= 255:
                            first_image_url = candidate
            except Exception as e:
                self.logger.error("Failed to parse card: %s", e, exc_info=True)

        if first_image_url:
            catalog.image = first_image_url
            await db.flush()

        self.logger.info("Parsed %d products from %s", len(products), _ONSTOCK_URL)
        return products

    def _parse_card(self, item, catalog_id: int, brand_id: int) -> Dict | None:
        link = item.select_one("a[href]")
        if not link:
            return None
        product_url = self._abs_url(link["href"])

        # The card name is the trailing <span> of the link (the first span
        # wraps rollover images).
        name_el = link.select("span")
        raw_name = ""
        for span in reversed(name_el):
            text = clean_text(span.get_text())
            if text:
                raw_name = text
                break
        if not raw_name:
            return None
        name = clean_product_name(raw_name)

        price_el = item.select_one(".price")
        price = self.extract_price(price_el.get_text(strip=True)) if price_el else 0
        if not price:
            self.logger.warning("No price for %s — skipping", raw_name)
            return None

        # Skip badge icons (novinka/star), take the first real product photo.
        image_urls: List[str] = []
        for img in item.select("img"):
            src = img.get("src") or ""
            if not src or "novinka" in src or "/star/" in src:
                continue
            image_urls = self.collect_image_urls([src])
            break

        return {
            "name": name,
            "slug": generate_slug(name),
            "description": "",
            "attributes": {},
            "source_url": product_url,
            "original_price": price,
            "catalog_id": catalog_id,
            "brand_id": brand_id,
            "image_urls": image_urls,
            "meta_title": name,
            "meta_description": "",
            "in_stock": True,
        }
