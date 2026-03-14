import uuid
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import UploadFile
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.banner import Banner

# ── Media ──

MEDIA_DIR = Path("/app/media/banners")
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}


def save_image(file: UploadFile) -> str:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "image.jpg").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(f"Unsupported file format: {ext}")
    filename = f"{uuid.uuid4().hex}{ext}"
    with open(MEDIA_DIR / filename, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return f"/media/banners/{filename}"


def remove_image(url: str):
    if not url:
        return
    path = Path("/app") / url.lstrip("/")
    path.unlink(missing_ok=True)


def _add_is_archived(banner: Banner) -> dict:
    data = {c.name: getattr(banner, c.name) for c in banner.__table__.columns}
    now = datetime.now(timezone.utc)
    expires = banner.expires_at
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    data["is_archived"] = bool(expires and expires < now)
    return data


# ── Queries ──

async def get_active(db: AsyncSession) -> List[Banner]:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Banner)
        .where(
            Banner.is_active == True,
            or_(Banner.expires_at == None, Banner.expires_at > now),
        )
        .order_by(Banner.sort_order.asc(), Banner.created_at.desc())
    )
    return list(result.scalars().all())


async def get_all(db: AsyncSession) -> List[dict]:
    result = await db.execute(
        select(Banner).order_by(Banner.sort_order.asc(), Banner.created_at.desc())
    )
    return [_add_is_archived(b) for b in result.scalars().all()]


async def get_by_id(db: AsyncSession, banner_id: int) -> Optional[Banner]:
    return await db.get(Banner, banner_id)


async def create(
    db: AsyncSession,
    image: UploadFile,
    *,
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
    href: Optional[str] = None,
    badge: Optional[str] = None,
    text_color: str = "light",
    show_button: bool = True,
    expires_at: Optional[datetime] = None,
    sort_order: int = 0,
    is_active: bool = True,
) -> Banner:
    image_url = save_image(image)
    banner = Banner(
        image_url=image_url,
        title=title,
        subtitle=subtitle,
        href=href,
        badge=badge,
        text_color=text_color,
        show_button=show_button,
        expires_at=expires_at,
        sort_order=sort_order,
        is_active=is_active,
    )
    db.add(banner)
    await db.commit()
    await db.refresh(banner)
    return banner


async def update(
    db: AsyncSession,
    banner: Banner,
    *,
    image: Optional[UploadFile] = None,
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
    href: Optional[str] = None,
    badge: Optional[str] = None,
    text_color: Optional[str] = None,
    show_button: Optional[bool] = None,
    expires_at: Optional[datetime] = None,
    clear_expires_at: bool = False,
    sort_order: Optional[int] = None,
    is_active: Optional[bool] = None,
) -> Banner:
    if image and image.filename:
        remove_image(banner.image_url)
        banner.image_url = save_image(image)

    if title is not None:
        banner.title = title or None
    if subtitle is not None:
        banner.subtitle = subtitle or None
    if href is not None:
        banner.href = href or None
    if badge is not None:
        banner.badge = badge or None
    if text_color is not None:
        banner.text_color = text_color
    if show_button is not None:
        banner.show_button = show_button
    if clear_expires_at:
        banner.expires_at = None
    elif expires_at is not None:
        banner.expires_at = expires_at
    if sort_order is not None:
        banner.sort_order = sort_order
    if is_active is not None:
        banner.is_active = is_active

    await db.commit()
    await db.refresh(banner)
    return banner


async def toggle_status(db: AsyncSession, banner: Banner) -> Banner:
    banner.is_active = not banner.is_active
    await db.commit()
    await db.refresh(banner)
    return banner


async def restore(db: AsyncSession, banner_id: int) -> Optional[Banner]:
    banner = await db.get(Banner, banner_id)
    if banner:
        banner.expires_at = None
        banner.is_active = True
        await db.commit()
        await db.refresh(banner)
    return banner


async def reorder(db: AsyncSession, items: List[dict]) -> int:
    count = 0
    for item in items:
        banner = await db.get(Banner, item["id"])
        if banner:
            banner.sort_order = item["sort_order"]
            count += 1
    await db.commit()
    return count


async def delete(db: AsyncSession, banner: Banner):
    remove_image(banner.image_url)
    await db.delete(banner)
    await db.commit()