import logging
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.dependencies import get_db
from app.models.product import Product
from app.models.catalog import Catalog

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/", response_class=Response)
async def get_yml_feed(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.product_images))
        .where(Product.is_active == True, Product.price > 0)
        .limit(10000)
    )
    products = result.scalars().all()

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE yml_catalog SYSTEM "shops.dtd">',
        '<yml_catalog date="2026-03-28">',
        '<shop>',
        '  <name>Дверь In</name>',
        '  <company>ИП Широких Кирилл Вячеславович</company>',
        '  <url>https://dverin.pro</url>',
        '  <currencies>',
        '    <currency id="RUR" rate="1"/>',
        '  </currencies>',
        '  <categories>',
        '    <category id="1">Входные двери</category>',
        '  </categories>',
        '  <offers>',
    ]

    for p in products:
        image_url = ""
        if p.product_images:
            main = next((img for img in p.product_images if img.is_main), None)
            img = main or p.product_images[0]
            image_url = f"https://dverin.pro{img.url}" if img.url.startswith("/") else img.url

        price = int(p.discount_price or p.price)
        old_price = int(p.price) if p.discount_price else None

        desc = (p.description or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")[:500]
        name = p.name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        url = f"https://dverin.pro/product/{p.slug}"

        lines.append(f'    <offer id="{p.id}" available="true">')
        lines.append(f'      <url>{url}</url>')
        lines.append(f'      <price>{price}</price>')
        if old_price and old_price > price:
            lines.append(f'      <oldprice>{old_price}</oldprice>')
        lines.append(f'      <currencyId>RUR</currencyId>')
        lines.append(f'      <categoryId>1</categoryId>')
        if image_url:
            lines.append(f'      <picture>{image_url}</picture>')
        lines.append(f'      <name>{name}</name>')
        if desc:
            lines.append(f'      <description>{desc}</description>')
        lines.append(f'    </offer>')

    lines += ['  </offers>', '</shop>', '</yml_catalog>']

    xml = "\n".join(lines)
    return Response(content=xml, media_type="application/xml; charset=utf-8")