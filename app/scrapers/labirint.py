import json
import logging
from typing import Dict, List

from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession

from app.scrapers.base_scraper import BaseScraper
from app.utils.text_utils import generate_slug, clean_text

logger = logging.getLogger("labirint_scraper")


class LabirintScraper(BaseScraper):
    def __init__(self):
        super().__init__(
            brand_name="Лабиринт",
            brand_slug="labirint",
            base_url="https://labirintdoors.ru",
            logger_name="labirint_scraper",
        )

    async def parse_catalog(
            self,
            catalog_url: str,
            db: AsyncSession,
            brand_id: int,
            catalog_name: str = "",
    ) -> List[Dict]:
        catalog_url = self._abs_url(catalog_url)
        catalog_slug = catalog_url.rstrip("/").split("/")[-1]

        html = self.get_html(catalog_url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")

        if not catalog_name:
            h1 = soup.select_one("h1.catalog-01__title, h1")
            catalog_name = f"{h1.get_text(strip=True)}" if h1 else f"{catalog_slug}"

        catalog = await self.ensure_catalog(db, catalog_name, catalog_slug, brand_id)
        catalog_id = catalog.id

        items = soup.select("ul.products-list-01-list li.products-list-01-item")
        self.logger.info("Найдено %d карточек в каталоге %s", len(items), catalog_url)

        products: List[Dict] = []
        first_image_url = None

        for item in items:
            try:
                parsed = self._parse_product_card(item, catalog_id, brand_id)
                if parsed:
                    products.append(parsed)
                    if not first_image_url and parsed["image_urls"]:
                        first_image_url = parsed["image_urls"][0]
            except Exception as e:
                self.logger.error("Ошибка парсинга карточки: %s", e, exc_info=True)

        if first_image_url:
            catalog.image = first_image_url
            await db.flush()

        self.logger.info("Распарсено %d товаров из %s", len(products), catalog_url)
        return products


    def discover_catalogs(self, main_url: str) -> List[Dict[str, str]]:
        html = self.get_html(main_url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        catalogs = []
        seen_urls = set()

        for item in soup.select("li.product-sections-01-item"):
            link = item.select_one("a.product-sections-01-item__img-container")
            name_el = item.select_one(".product-sections-01-item__name")

            if not link or not link.get("href"):
                continue

            url = self._abs_url(link["href"])
            if url in seen_urls:
                continue
            seen_urls.add(url)

            name = name_el.get_text(strip=True) if name_el else ""
            catalogs.append({"url": url, "name": f"Лабиринт {name}"})
            self.logger.info("Найден каталог: %s → %s", name, url)

        return catalogs


    def _parse_product_card(
        self,
        item,
        catalog_id: int,
        brand_id: int,
    ) -> Dict | None:
        header = item.select_one(".products-list-01-item__header a")
        if not header or not header.get("href"):
            return None

        title = header.get_text(strip=True)
        product_url = self._abs_url(header.get("href"))

        # Загружаем страницу товара
        html = self.get_html(product_url)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")

        # Название
        name_el = soup.select_one(".product-01__title")
        name = name_el.get_text(strip=True) if name_el else title

        # Цена
        price_el = soup.select_one(".product-01__price")
        price = self.extract_price(price_el.get_text(strip=True)) if price_el else 0

        image_urls = self._extract_images(soup)
        attributes = self.extract_specs(soup)
        # Slug
        slug = generate_slug(name)

        return {
            "name": name,
            "slug": slug,
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
        for row in soup.select(".product-01__parameters-item"):
            term = row.select_one(".product-01__parameters-item-term")
            value = row.select_one(".product-01__parameters-item-dscr")
            if term and value:
                key = clean_text(term.get_text())
                val = clean_text(value.get_text())
                if key and val:
                    specs[key] = val
        return specs


    def _extract_description(self, soup: BeautifulSoup, name: str) -> str:
        parts: List[str] = []

        for selector in (
            ".product-01__benefits",
            ".product-01__parameters",
            ".product-01__description",
            ".product-description",
        ):
            el = soup.select_one(selector)
            if el:
                parts.append(clean_text(el.get_text()))

        # Характеристики
        specs: List[str] = []
        for row in soup.select(
            ".product-01__specifications .product-specifications-01__row"
        ):
            caption = row.select_one(".product-specifications-01__caption")
            value = row.select_one(".product-specifications-01__value")
            if caption and value:
                specs.append(f"{clean_text(caption.get_text())}: {clean_text(value.get_text())}")

        description = " ".join(parts).strip()
        if specs:
            description += "\n\nХарактеристики:\n" + "\n".join(specs)

        if not description.strip():
            description = (
                f"Входная дверь {name} от производителя. "
                "Качественная металлическая дверь с надежной защитой."
            )

        return description


    def _extract_images(self, soup: BeautifulSoup) -> List[str]:
        raw_urls: List[str] = []

        for img in soup.select(
            ".product-gallery-01__list img, .product-gallery-01__stage-item img"
        ):
            url = img.get("data-bc-lazy-path") or img.get("src")
            if url:
                raw_urls.append(url)

        for link in soup.select(".product-gallery-01__stage-item-img-container"):
            href = link.get("href")
            if href:
                raw_urls.append(href)

        for el in soup.select("[index]"):
            try:
                data = el.get("index")
                if data and isinstance(data, str):
                    obj = json.loads(data)
                    if isinstance(obj, dict):
                        for v in obj.values():
                            if isinstance(v, str) and v:
                                raw_urls.append(v)
            except (json.JSONDecodeError, Exception):
                pass

        # Резервный поиск
        if not raw_urls:
            for img in soup.select(
                ".product-01 img, .product-gallery img, "
                ".products-list-01-item__image img"
            ):
                src = img.get("src")
                if src:
                    raw_urls.append(src)

        image_urls = self.collect_image_urls(raw_urls)

        if not image_urls:
            image_urls = [f"{self.base_url}/images/no-photo.jpg"]

        return image_urls