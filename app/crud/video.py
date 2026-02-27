import logging
import os
import re
import uuid
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import List, Optional

from sqlalchemy import and_, delete as sa_delete, func, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import raise_400, raise_404, raise_429
from app.models.product import Product
from app.models.video import Video
from app.schemas.video import VideoCreate, VideoUpdate

logger = logging.getLogger(__name__)

# Derived from settings
VIDEOS_DIR = f"{settings.UPLOAD_DIR}/videos"
ALLOWED_VIDEO_EXTENSIONS = set(settings.ALLOWED_VIDEO_EXTENSIONS)
MAX_VIDEO_SIZE = settings.MAX_VIDEO_SIZE
MAX_UPLOADS_PER_USER = settings.MAX_UPLOADS_PER_USER
MAX_UPLOADS_GLOBAL = settings.MAX_UPLOADS_GLOBAL

# Constants (don't change between environments)
ALLOWED_CONTENT_TYPES = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/x-matroska", "video/webm"}
MAX_FILENAME_LENGTH = 100
FORBIDDEN_CHARS = set('<>:"|?*\0')

# Upload rate limiting (in-memory counter)
_upload_counts: dict[str, int] = defaultdict(int)


# === File validation & upload ===

def validate_video_file(filename: str, content_type: Optional[str]) -> str:
    if not filename or len(filename) > MAX_FILENAME_LENGTH:
        raise_400("Invalid filename length (max 100 chars)")

    if any(c in filename for c in FORBIDDEN_CHARS):
        raise_400("Invalid characters in filename")

    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise_400(f"Unsupported format. Allowed: {', '.join(ALLOWED_VIDEO_EXTENSIONS)}")

    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise_400(f"Invalid content type: {content_type}")

    return ext


def check_upload_limits(username: str) -> None:
    user_count = _upload_counts[username]
    total_count = sum(_upload_counts.values())

    if user_count >= MAX_UPLOADS_PER_USER:
        raise_429(f"User upload limit reached ({MAX_UPLOADS_PER_USER}/hour)")
    if total_count >= MAX_UPLOADS_GLOBAL:
        raise_429(f"Global upload limit reached ({MAX_UPLOADS_GLOBAL}/hour)")


def register_upload(username: str) -> None:
    _upload_counts[username] += 1


def get_upload_stats(username: Optional[str] = None) -> dict:
    return {
        "user_uploads": _upload_counts.get(username, 0) if username else None,
        "total_uploads": sum(_upload_counts.values()),
        "user_limit": MAX_UPLOADS_PER_USER,
        "global_limit": MAX_UPLOADS_GLOBAL,
        "by_user": dict(_upload_counts),
    }


def reset_upload_limits() -> dict:
    old = dict(_upload_counts)
    _upload_counts.clear()
    return old


async def save_upload(file, username: str) -> str:
    """Stream-save uploaded file, return relative URL path."""
    validate_video_file(file.filename, file.content_type)
    check_upload_limits(username)

    file_uuid = str(uuid.uuid4())
    base_name = os.path.splitext(file.filename)[0]
    safe_name = "".join(c for c in base_name if c.isalnum() or c in (" ", "-", "_")).strip()[:50]
    output_filename = f"{file_uuid}_{safe_name}.mp4"
    final_path = os.path.join(VIDEOS_DIR, output_filename)

    os.makedirs(VIDEOS_DIR, exist_ok=True)

    try:
        total_size = 0
        with open(final_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_VIDEO_SIZE:
                    os.unlink(final_path)
                    raise_400(f"File too large (max {MAX_VIDEO_SIZE // (1024 * 1024)}MB)")
                f.write(chunk)

        try:
            os.chmod(final_path, 0o644)
        except OSError:
            pass

        register_upload(username)
        logger.info("Video saved: %s (%d bytes) by %s", output_filename, total_size, username)
        return f"/media/videos/{output_filename}"

    except Exception:
        if os.path.exists(final_path):
            os.unlink(final_path)
        raise


def _delete_file(url: Optional[str]) -> None:
    if not url or not url.startswith("/media/"):
        return
    path = Path(settings.UPLOAD_DIR) / url[7:]
    if path.exists():
        try:
            path.unlink()
        except Exception as e:
            logger.error("Failed to delete %s: %s", path, e)


# === CRUD ===

async def create(db: AsyncSession, data: VideoCreate) -> Video:
    video = Video(**data.model_dump())
    db.add(video)
    await db.commit()
    await db.refresh(video)
    return video


async def get_by_id(db: AsyncSession, video_id: int) -> Optional[Video]:
    result = await db.execute(select(Video).where(Video.id == video_id))
    return result.scalar_one_or_none()


async def get_by_uuid(db: AsyncSession, video_uuid: str) -> Optional[Video]:
    result = await db.execute(select(Video).where(Video.uuid == video_uuid))
    return result.scalar_one_or_none()


async def get_all(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None,
    is_featured: Optional[bool] = None,
    product_id: Optional[int] = None,
) -> List[Video]:
    query = select(Video)
    filters = []
    if is_active is not None:
        filters.append(Video.is_active == is_active)
    if is_featured is not None:
        filters.append(Video.is_featured == is_featured)
    if product_id is not None:
        filters.append(Video.product_id == product_id)
    if filters:
        query = query.where(and_(*filters))
    query = query.order_by(Video.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_by_product(db: AsyncSession, product_id: int) -> List[Video]:
    result = await db.execute(
        select(Video).where(Video.product_id == product_id).order_by(Video.created_at.desc())
    )
    return list(result.scalars().all())


async def get_featured(db: AsyncSession, limit: int = 10) -> List[Video]:
    result = await db.execute(
        select(Video)
        .where(and_(Video.is_active == True, Video.is_featured == True))
        .order_by(Video.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def search(db: AsyncSession, query_text: str) -> List[Video]:
    result = await db.execute(
        select(Video)
        .where(and_(Video.is_active == True, Video.title.ilike(f"%{query_text}%")))
        .order_by(Video.created_at.desc())
    )
    return list(result.scalars().all())


async def update(db: AsyncSession, video_id: int, data: VideoUpdate) -> Optional[Video]:
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        return await get_by_id(db, video_id)
    await db.execute(sa_update(Video).where(Video.id == video_id).values(**update_data))
    await db.commit()
    return await get_by_id(db, video_id)


async def remove(db: AsyncSession, video_id: int) -> bool:
    video = await get_by_id(db, video_id)
    if not video:
        return False
    _delete_file(video.url)
    _delete_file(video.thumbnail_url)
    await db.execute(sa_delete(Video).where(Video.id == video_id))
    await db.commit()
    return True


async def toggle_status(db: AsyncSession, video_id: int) -> Optional[Video]:
    video = await get_by_id(db, video_id)
    if not video:
        return None
    return await update(db, video_id, VideoUpdate(is_active=not video.is_active))


async def toggle_featured(db: AsyncSession, video_id: int) -> Optional[Video]:
    video = await get_by_id(db, video_id)
    if not video:
        return None
    return await update(db, video_id, VideoUpdate(is_featured=not video.is_featured))


# === Stats (DB queries, not loading all rows) ===

async def get_stats(db: AsyncSession) -> dict:
    total = (await db.execute(select(func.count(Video.id)))).scalar() or 0
    active = (await db.execute(
        select(func.count(Video.id)).where(Video.is_active == True)
    )).scalar() or 0
    featured = (await db.execute(
        select(func.count(Video.id)).where(and_(Video.is_active == True, Video.is_featured == True))
    )).scalar() or 0
    with_products = (await db.execute(
        select(func.count(Video.id)).where(Video.product_id.isnot(None))
    )).scalar() or 0

    return {
        "total_videos": total,
        "active_videos": active,
        "inactive_videos": total - active,
        "featured_videos": featured,
        "with_products": with_products,
        "without_products": total - with_products,
    }


# === Product linking ===

async def find_product_by_title(db: AsyncSession, video_title: str) -> Optional[Product]:
    cleaned = re.sub(r'[^\w\s]', '', video_title.lower()).strip()
    result = await db.execute(select(Product).where(Product.is_active == True))
    products = result.scalars().all()

    best_match = None
    best_score = 0.0

    for product in products:
        name = re.sub(r'[^\w\s]', '', product.name.lower()).strip()
        if name in cleaned or cleaned in name:
            return product
        score = SequenceMatcher(None, cleaned, name).ratio()
        if score > best_score and score > 0.6:
            best_score = score
            best_match = product

    return best_match


async def auto_link(db: AsyncSession, video_id: int) -> Optional[Video]:
    video = await get_by_id(db, video_id)
    if not video or video.product_id:
        return video
    product = await find_product_by_title(db, video.title)
    if product:
        return await update(db, video_id, VideoUpdate(product_id=product.id))
    return video


async def suggest_products(db: AsyncSession, video_title: str, limit: int = 5) -> list[tuple]:
    cleaned = re.sub(r'[^\w\s]', '', video_title.lower()).strip()
    result = await db.execute(select(Product).where(Product.is_active == True))
    products = result.scalars().all()

    suggestions = []
    for product in products:
        name = re.sub(r'[^\w\s]', '', product.name.lower()).strip()
        score = SequenceMatcher(None, cleaned, name).ratio()
        if score > 0.3:
            suggestions.append((product, score))

    suggestions.sort(key=lambda x: x[1], reverse=True)
    return suggestions[:limit]


# === System check ===

def system_check(username: str) -> dict:
    import shutil

    media_exists = os.path.exists(settings.UPLOAD_DIR)
    media_writable = os.access(settings.UPLOAD_DIR, os.W_OK) if media_exists else False

    checks = {
        "media_dir_exists": media_exists,
        "media_dir_writable": media_writable,
    }

    if media_exists:
        total, used, free = shutil.disk_usage(settings.UPLOAD_DIR)
        checks["disk_free_mb"] = free // (1024 * 1024)

    checks["upload_stats"] = get_upload_stats(username)

    ready = media_exists and media_writable and checks.get("disk_free_mb", 0) > 100
    return {"status": "OK" if ready else "ERROR", "checks": checks}