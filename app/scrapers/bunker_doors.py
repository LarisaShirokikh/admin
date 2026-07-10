"""Скрапер официального сайта Бункера bunkerdoors.ru.

Переписан 2026-07-10 под новую архитектуру BaseScraper (диф-синк, content_hash,
category_rules) по образцу labirint.py. Сайт донора на том же движке, что и
labirintdoors.ru (шаблоны «*-01»), поэтому селекторы совпадают с Лабиринтом.

Структура донора:
  /prod/<серия>/<bn-NN>   — страница модели (серии: bunker-base/hit/prime/termo)
  /<bn-NN-отделка-цвет>   — карточка конечного товара-варианта (в корне сайта)
Каталог магазина = модель BN-NN, товар = вариант. Полный список вариантов
модели берём из sitemap.xml по префиксу slug (на странице модели lazy-пагинация).
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

# Серии донора → человекочитаемое имя (для названия каталога)
_SERIES_NAMES = {
    "bunker-base": "Базовая",
    "bunker-hit": "Хит",
    "bunker-prime": "Прайм",
    "bunker-termo": "Термо",
}


def model_catalog_name(model_slug: str, series_slug: str = "") -> str:
    """bn-03 + bunker-hit → «Бункер БН-03 Хит»."""
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

    # ── Sitemap донора ───────────────────────────────────────────────────

    def _get_sitemap_slugs(self) -> List[str]:
        """Кеш всех корневых slug'ов из sitemap.xml (товары-варианты)."""
        if self._sitemap_slugs is not None:
            return self._sitemap_slugs
        xml = self.get_html(f"{self.base_url}/sitemap.xml") or ""
        slugs: List[str] = []
        # Только <loc> — regex вместо XML-парсера (XXE-безопасно)
        for url in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml):
            path = url.replace(self.base_url, "").strip("/")
            if "/" in path or not path:
                continue
            if _VARIANT_SLUG_RE.match(path):
                slugs.append(path)
        self._sitemap_slugs = slugs
        self.logger.info("В sitemap донора %d товаров-вариантов", len(slugs))
        return slugs

    # ── Обнаружение каталогов (моделей) ──────────────────────────────────

    def discover_catalogs(self, main_url: str) -> List[Dict[str, str]]:
        """Модели выводим из товаров-вариантов sitemap (у части моделей нет
        своей страницы /prod/... в sitemap — например BN-02, BN-12…BN-15)."""
        xml = self.get_html(f"{self.base_url}/sitemap.xml") or ""

        # серия модели, если страница модели есть в sitemap
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
            # псевдо-URL для моделей без страницы: parse_catalog берёт slug из хвоста
            url = model_urls.get(model_slug, f"{self.base_url}/prod/x/{model_slug}")
            catalogs.append({"url": url, "name": name})
            self.logger.info("Найдена модель: %s → %s", name, url)
        return catalogs

    # ── Парсинг каталога (модели) ────────────────────────────────────────

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
            self.logger.error("Не похоже на URL модели Бункера: %s", catalog_url)
            return []
        model_slug = tail.group(1)
        catalog_slug = model_slug  # slug каталога = slug модели (bn-03)

        if not catalog_name:
            m = _MODEL_URL_RE.search(catalog_url)
            catalog_name = model_catalog_name(model_slug, m.group(1) if m else "")

        catalog = await self.ensure_catalog(db, catalog_name, catalog_slug, brand_id)
        catalog_id = catalog.id

        # Варианты модели: страница модели (может быть обрезана lazy-пагинацией)
        # + sitemap по префиксу slug — объединяем для полноты.
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

        self.logger.info("Модель %s: %d вариантов", model_slug, len(variant_slugs))

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
                        first_image_url = parsed["image_urls"][0]
            except Exception as e:
                self.logger.error("Ошибка парсинга %s: %s", slug, e, exc_info=True)

        if first_image_url:
            catalog.image = first_image_url
            await db.flush()

        self.logger.info("Распарсено %d товаров из %s", len(products), catalog_url)
        return products

    # ── Парсинг карточки варианта ────────────────────────────────────────

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

        # Основной источник — JSON-LD Product, который донор кладёт в <head>
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
            self.logger.warning("Нет цены у %s — пропуск", product_url)
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

        # Основной источник — JSON-LD (оригиналы). Селекторы галереи не используем:
        # у донора Angular-галерея, а data-bc-lazy теги включают баннеры/логотипы.
        ld_images = ld.get("image")
        if isinstance(ld_images, list):
            raw_urls.extend(u for u in ld_images if isinstance(u, str))
        elif isinstance(ld_images, str):
            raw_urls.append(ld_images)

        # Фолбэк: og:image, если JSON-LD пуст
        if not raw_urls:
            og = soup.select_one('meta[property="og:image"]')
            if og and og.get("content"):
                raw_urls.append(og["content"])

        return self.collect_image_urls(raw_urls)
