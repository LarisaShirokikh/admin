"""Scraper for the official Bunker site bunkerdoors.ru.

Rewritten 2026-07-10 for the current BaseScraper architecture (diff-sync,
content_hash, category_rules), modeled after labirint.py. The donor runs the
same engine as labirintdoors.ru ("*-01" templates), so most selectors match.

Donor structure:
  /prod/<series>/<bn-NN>   — model page (series: bunker-base/hit/prime/termo)
  /<bn-NN-finish-color>    — final product variant page (site root)
Shop catalog = model BN-NN, product = variant. The full variant list per model
comes from sitemap.xml by slug prefix (model pages use lazy pagination).
"""
import json
import logging
import re
from typing import Dict, List, Optional

from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession

from app.scrapers.base_scraper import BaseScraper
from app.utils.text_utils import generate_slug, clean_text

logger = logging.getLogger("bunker_scraper")

_MODEL_URL_RE = re.compile(r"/prod/([a-z0-9-]+)/(bn-\d+)/?$")
_VARIANT_SLUG_RE = re.compile(r"^(?:vhodnaya-dver-)?(bn-\d+)")

# Donor series slug → human-readable name (used in catalog titles)
_SERIES_NAMES = {
    "bunker-base": "Базовая",
    "bunker-hit": "Хит",
    "bunker-prime": "Прайм",
    "bunker-termo": "Термо",
}

# catalog.image column is varchar(255); donor has long percent-encoded URLs
_MAX_IMAGE_URL_LEN = 255


def model_catalog_name(model_slug: str, series_slug: str = "") -> str:
    """bn-03 + bunker-hit → 'Бункер БН-03 Хит'."""
    model = model_slug.upper().replace("BN-", "БН-")
    series = _SERIES_NAMES.get(series_slug, "")
    return f"Бункер {model} {series}".strip()


class BunkerDoorsScraper(BaseScraper):
    def __init__(self):
        super().__init__(
            brand_name="Бункер",
            brand_slug="bunker",
            base_url="https://bunkerdoors.ru",
            logger_name="bunker_scraper",
        )
        self._sitemap_slugs: Optional[List[str]] = None

    # ── Donor sitemap ────────────────────────────────────────────────────

    def _get_sitemap_slugs(self) -> List[str]:
        """Cached root-level slugs from sitemap.xml (product variants)."""
        if self._sitemap_slugs is not None:
            return self._sitemap_slugs
        xml = self.get_html(f"{self.base_url}/sitemap.xml") or ""
        slugs: List[str] = []
        # Only <loc> values are needed — regex instead of an XML parser (XXE-safe)
        for url in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml):
            path = url.replace(self.base_url, "").strip("/")
            if "/" in path or not path:
                continue
            if _VARIANT_SLUG_RE.match(path):
                slugs.append(path)
        self._sitemap_slugs = slugs
        self.logger.info("Donor sitemap has %d product variants", len(slugs))
        return slugs

    # ── Catalog (model) discovery ────────────────────────────────────────

    def discover_catalogs(self, main_url: str) -> List[Dict[str, str]]:
        """Models are derived from variant slugs: some models (BN-02, BN-12..15)
        have no /prod/... page in the sitemap at all."""
        xml = self.get_html(f"{self.base_url}/sitemap.xml") or ""

        series_by_model: Dict[str, str] = {}
        model_urls: Dict[str, str] = {}
        for url in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml):
            m = _MODEL_URL_RE.search(url)
            if m:
                series_by_model[m.group(2)] = m.group(1)
                model_urls[m.group(2)] = url

        models: List[str] = []
        for slug in self._get_sitemap_slugs():
            m = _VARIANT_SLUG_RE.match(slug)
            if m and m.group(1) not in models:
                models.append(m.group(1))

        catalogs: List[Dict[str, str]] = []
        for model_slug in sorted(models):
            series_slug = series_by_model.get(model_slug, "")
            name = model_catalog_name(model_slug, series_slug)
            # pseudo-URL for pageless models: parse_catalog reads the slug from the tail
            url = model_urls.get(model_slug, f"{self.base_url}/prod/x/{model_slug}")
            catalogs.append({"url": url, "name": name})
            self.logger.info("Discovered model: %s → %s", name, url)
        return catalogs

    # ── Catalog (model) parsing ──────────────────────────────────────────

    async def parse_catalog(
        self,
        catalog_url: str,
        db: AsyncSession,
        brand_id: int,
        catalog_name: str = "",
    ) -> List[Dict]:
        catalog_url = self._abs_url(catalog_url)
        tail = re.search(r"(bn-\d+)/?$", catalog_url)
        if not tail:
            self.logger.error("Not a Bunker model URL: %s", catalog_url)
            return []
        model_slug = tail.group(1)
        catalog_slug = model_slug

        if not catalog_name:
            m = _MODEL_URL_RE.search(catalog_url)
            catalog_name = model_catalog_name(model_slug, m.group(1) if m else "")

        catalog = await self.ensure_catalog(db, catalog_name, catalog_slug, brand_id)
        catalog_id = catalog.id

        # Variants: model page listing (may be cut by lazy pagination)
        # merged with sitemap slugs by model prefix for completeness.
        variant_slugs: List[str] = []
        html = self.get_html(catalog_url)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.select(".products-list-01-item__header a"):
                href = (a.get("href") or "").strip("/")
                if href and _VARIANT_SLUG_RE.match(href):
                    variant_slugs.append(href.split("/")[-1])
        for slug in self._get_sitemap_slugs():
            sm = _VARIANT_SLUG_RE.match(slug)
            if sm and sm.group(1) == model_slug:
                variant_slugs.append(slug)
        variant_slugs = list(dict.fromkeys(variant_slugs))

        self.logger.info("Model %s: %d variants", model_slug, len(variant_slugs))

        products: List[Dict] = []
        first_image_url = None
        for slug in variant_slugs:
            try:
                parsed = self._parse_product_page(
                    f"{self.base_url}/{slug}", catalog_id, brand_id
                )
                if parsed:
                    products.append(parsed)
                    if not first_image_url and parsed["image_urls"]:
                        candidate = parsed["image_urls"][0]
                        if len(candidate) <= _MAX_IMAGE_URL_LEN:
                            first_image_url = candidate
            except Exception as e:
                self.logger.error("Failed to parse %s: %s", slug, e, exc_info=True)

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

        # Primary source is the JSON-LD Product block the donor puts in <head>
        ld = self._extract_json_ld(soup)
        name = (ld.get("name") or "").strip()
        if not name:
            title_el = soup.select_one(".product-01__title, h1")
            name = title_el.get_text(strip=True) if title_el else ""
        if not name:
            return None

        price = 0
        offers = ld.get("offers") or {}
        if isinstance(offers, dict) and offers.get("price"):
            try:
                price = int(float(offers["price"]))
            except (TypeError, ValueError):
                price = 0
        if not price:
            price_el = soup.select_one(".product-01__price")
            price = self.extract_price(price_el.get_text(strip=True)) if price_el else 0
        if not price:
            self.logger.warning("No price at %s — skipping", product_url)
            return None

        image_urls = self._extract_images(soup, ld)
        attributes = self.extract_specs(soup)

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

    @staticmethod
    def _extract_json_ld(soup: BeautifulSoup) -> dict:
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(data, dict) and data.get("@type") == "Product":
                return data
        return {}

    def extract_specs(self, soup: BeautifulSoup) -> dict:
        specs = {}
        for row in soup.select(".product-01__parameters-item"):
            term = row.select_one(".product-01__parameters-item-term")
            value = row.select_one(".product-01__parameters-item-dscr")
            if term and value:
                key = clean_text(term.get_text())
                val = clean_text(value.get_text())
                if key and val:
                    specs[key] = val
        return specs

    def _extract_images(self, soup: BeautifulSoup, ld: dict) -> List[str]:
        raw_urls: List[str] = []

        # JSON-LD carries the original-size image; gallery selectors are not
        # used on purpose: the donor gallery is Angular-rendered and lazy-load
        # tags there include banners and logos.
        ld_images = ld.get("image")
        if isinstance(ld_images, list):
            raw_urls.extend(u for u in ld_images if isinstance(u, str))
        elif isinstance(ld_images, str):
            raw_urls.append(ld_images)

        if not raw_urls:
            og = soup.select_one('meta[property="og:image"]')
            if og and og.get("content"):
                raw_urls.append(og["content"])

        return self.collect_image_urls(raw_urls)
