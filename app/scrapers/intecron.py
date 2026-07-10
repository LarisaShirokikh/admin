"""Scraper for the official Intecron site intecron-msk.ru (Bitrix).

Rewritten 2026-07-10 for the current BaseScraper architecture (diff-sync,
content_hash, category_rules), modeled after labirint.py/bunker_doors.py.

Donor structure:
  /catalog/intekron/                       — list of series
  /catalog/intekron/<series>/              — series page with variant links
  /catalog/intekron/<series>/<variant>/    — product variant page
Shop catalog = series ("Интекрон Гектор"), product = variant.
Variant page: h1 name, #price_value[data-value] price, .specific-tbl specs,
first /upload/iblock image as the photo.
"""
import logging
import re
from typing import Dict, List

from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession

from app.scrapers.base_scraper import BaseScraper
from app.utils.text_utils import generate_slug, clean_text

logger = logging.getLogger("intecron_scraper")

_SERIES_URL_RE = re.compile(r"/catalog/intekron/([a-z0-9_]+)/?$")
_VARIANT_URL_RE = re.compile(r"/catalog/intekron/[a-z0-9_]+/([a-z0-9_]+)/?$")

# Attributes that are shop flags on the donor side, useless as product specs
_SKIP_SPEC_KEYS = ("Новинка", "Акция", "Распродажа")


def clean_catalog_name(raw: str) -> str:
    name = raw or ""
    name = re.sub(r"входн(ые|ая)\s+двер(и|ь)", "", name, flags=re.IGNORECASE)
    name = re.sub(r"интекрон", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+", " ", name).strip(" -—.,«»\"'")
    return f"Интекрон {name}".strip() if name else "Интекрон"


class IntecronScraper(BaseScraper):
    def __init__(self):
        super().__init__(
            brand_name="Интекрон",
            brand_slug="intecron",
            base_url="https://intecron-msk.ru",
            logger_name="intecron_scraper",
        )

    # ── Series discovery ─────────────────────────────────────────────────

    def discover_catalogs(self, main_url: str) -> List[Dict[str, str]]:
        html = self.get_html(f"{self.base_url}/catalog/intekron/")
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")

        catalogs: List[Dict[str, str]] = []
        seen = set()
        for a in soup.select('a[href^="/catalog/intekron/"]'):
            href = a.get("href") or ""
            m = _SERIES_URL_RE.search(href)
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            url = self._abs_url(href)
            catalogs.append({"url": url, "name": ""})  # name resolved in parse_catalog
            self.logger.info("Discovered series: %s", url)
        return catalogs

    # ── Series parsing ───────────────────────────────────────────────────

    async def parse_catalog(
        self,
        catalog_url: str,
        db: AsyncSession,
        brand_id: int,
        catalog_name: str = "",
    ) -> List[Dict]:
        catalog_url = self._abs_url(catalog_url)
        m = _SERIES_URL_RE.search(catalog_url)
        if not m:
            self.logger.error("Not an Intecron series URL: %s", catalog_url)
            return []
        catalog_slug = m.group(1)

        html = self.get_html(catalog_url)
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")

        if not catalog_name:
            h1 = soup.select_one("h1")
            catalog_name = clean_catalog_name(
                h1.get_text(strip=True) if h1 else catalog_slug
            )

        catalog = await self.ensure_catalog(db, catalog_name, catalog_slug, brand_id)
        catalog_id = catalog.id

        variant_urls: List[str] = []
        prefix = f"/catalog/intekron/{catalog_slug}/"
        for a in soup.select(f'a[href^="{prefix}"]'):
            href = a.get("href") or ""
            if _VARIANT_URL_RE.search(href):
                variant_urls.append(self._abs_url(href))
        variant_urls = list(dict.fromkeys(variant_urls))

        self.logger.info("Series %s: %d variants", catalog_slug, len(variant_urls))

        products: List[Dict] = []
        first_image_url = None
        for url in variant_urls:
            try:
                parsed = self._parse_product_page(url, catalog_id, brand_id)
                if parsed:
                    products.append(parsed)
                    if not first_image_url and parsed["image_urls"]:
                        candidate = parsed["image_urls"][0]
                        if len(candidate) <= 255:
                            first_image_url = candidate
            except Exception as e:
                self.logger.error("Failed to parse %s: %s", url, e, exc_info=True)

        if first_image_url:
            catalog.image = first_image_url
            await db.flush()

        self.logger.info("Parsed %d products from %s", len(products), catalog_url)
        return products

    # ── Variant page parsing ─────────────────────────────────────────────

    def _parse_product_page(
        self,
        product_url: str,
        catalog_id: int,
        brand_id: int,
    ) -> Dict | None:
        html = self.get_html(product_url)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")

        h1 = soup.select_one("h1")
        if not h1:
            return None
        raw_name = h1.get_text(strip=True)
        name = f"Входная дверь Интекрон {raw_name}"

        price = 0
        price_el = soup.select_one("#price_value")
        if price_el and price_el.get("data-value"):
            try:
                price = int(float(price_el["data-value"]))
            except (TypeError, ValueError):
                price = 0
        if not price and price_el:
            price = self.extract_price(price_el.get_text(strip=True))
        if not price:
            self.logger.warning("No price at %s — skipping", product_url)
            return None

        attributes = self.extract_specs(soup)
        image_urls = self._extract_images(soup)

        return {
            "name": name,
            "slug": generate_slug(name),
            "description": "",
            "attributes": attributes,
            "source_url": product_url,
            "original_price": price,
            "catalog_id": catalog_id,
            "brand_id": brand_id,
            "image_urls": image_urls,
            "meta_title": name,
            "meta_description": "",
            "in_stock": True,
        }

    def extract_specs(self, soup: BeautifulSoup) -> dict:
        specs = {}
        for row in soup.select(".specific-tbl table tr"):
            th = row.select_one("th")
            td = row.select_one("td")
            if not th or not td:
                continue
            key = clean_text(th.get_text()).rstrip(":")
            val = clean_text(td.get_text())
            if key and val and key not in _SKIP_SPEC_KEYS:
                specs[key] = val
        return specs

    def _extract_images(self, soup: BeautifulSoup) -> List[str]:
        # The main photo is the first /upload/iblock image on the page;
        # the rest are mostly "similar products" thumbnails.
        for img in soup.select('img[src*="/upload/"]'):
            src = img.get("src") or ""
            if "/upload/iblock/" in src and src.lower().endswith(
                (".jpg", ".jpeg", ".png", ".webp")
            ):
                return self.collect_image_urls([src])
        return []
