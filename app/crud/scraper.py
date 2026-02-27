import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings, active_scraping_tasks
from app.core.exceptions import raise_400, raise_429
from app.models.admin import AdminUser
from app.models.category import Category
from app.schemas.scraper import ScraperType

logger = logging.getLogger(__name__)


# === Scraper registry ===

@dataclass
class ScraperConfig:
    task: Callable
    name: str
    base_url: Optional[str] = None


def _build_registry() -> dict[ScraperType, ScraperConfig]:
    from app.worker.tasks import (
        scrape_labirint_multiple_catalogs_task,
        scrape_bunker_doors_multiple_catalogs_task,
        scrape_intecron_multiple_catalogs_task,
        scrape_as_doors_multiple_catalogs_task,
    )
    return {
        ScraperType.LABIRINT: ScraperConfig(task=scrape_labirint_multiple_catalogs_task, name="Labirint"),
        ScraperType.BUNKER: ScraperConfig(task=scrape_bunker_doors_multiple_catalogs_task, name="Bunker Doors", base_url="https://bunkerdoors.ru"),
        ScraperType.INTECRON: ScraperConfig(task=scrape_intecron_multiple_catalogs_task, name="Intecron", base_url="https://intecron-msk.ru"),
        ScraperType.AS_DOORS: ScraperConfig(task=scrape_as_doors_multiple_catalogs_task, name="AS-Doors", base_url="https://as-doors.ru"),
    }


_registry: Optional[dict[ScraperType, ScraperConfig]] = None


def get_registry() -> dict[ScraperType, ScraperConfig]:
    global _registry
    if _registry is None:
        _registry = _build_registry()
    return _registry


def get_config(scraper_type: ScraperType) -> ScraperConfig:
    return get_registry()[scraper_type]


def _get_task_names() -> list[str]:
    return [cfg.task.name for cfg in get_registry().values()]


# === Category checks ===

async def check_categories(db: AsyncSession) -> dict:
    active = (await db.execute(
        select(func.count(Category.id)).where(Category.is_active == True)
    )).scalar() or 0
    total = (await db.execute(
        select(func.count(Category.id))
    )).scalar() or 0
    return {"active_categories": active, "total_categories": total, "has_categories": active > 0}


async def require_categories(db: AsyncSession) -> dict:
    info = await check_categories(db)
    if not info["has_categories"]:
        raise_400("No active categories. Create at least one before scraping.")
    return info


# === Task counter management ===

def sync_counters() -> dict:
    try:
        from celery import current_app
        inspect = current_app.control.inspect()
        active_tasks = inspect.active()

        if not active_tasks:
            cleared = sum(active_scraping_tasks.values())
            active_scraping_tasks.clear()
            logger.info("SYNC: No active Celery tasks, cleared %d counters", cleared)
            return {"cleared": cleared, "active_scraper_tasks": 0}

        task_names = set(_get_task_names())
        active_ids = set()
        for worker_tasks in active_tasks.values():
            if worker_tasks:
                for task in worker_tasks:
                    if task.get("name") in task_names:
                        active_ids.add(task["id"])

        if not active_ids:
            cleared = sum(active_scraping_tasks.values())
            active_scraping_tasks.clear()
            logger.info("SYNC: No active scraper tasks, cleared %d counters", cleared)
            return {"cleared": cleared, "active_scraper_tasks": 0}

        current_total = sum(active_scraping_tasks.values())
        real_total = len(active_ids)

        if current_total > real_total and current_total > 0:
            ratio = real_total / current_total
            for username in active_scraping_tasks:
                active_scraping_tasks[username] = max(0, int(active_scraping_tasks[username] * ratio))
            logger.info("SYNC: Adjusted counters %d -> %d", current_total, real_total)

        return {"synced": True, "active_scraper_tasks": real_total, "counters": dict(active_scraping_tasks)}

    except Exception as e:
        logger.error("SYNC failed: %s", e)
        return {"error": str(e), "synced": False}


def check_limits(user: AdminUser) -> None:
    sync_counters()
    user_tasks = active_scraping_tasks[user.username]
    total_tasks = sum(active_scraping_tasks.values())

    if user_tasks >= settings.MAX_CONCURRENT_TASKS_PER_USER:
        raise_429(f"User task limit reached ({settings.MAX_CONCURRENT_TASKS_PER_USER})")
    if total_tasks >= settings.MAX_CONCURRENT_TASKS_GLOBAL:
        raise_429(f"Global task limit reached ({settings.MAX_CONCURRENT_TASKS_GLOBAL})")


def register_task(user: AdminUser, task_id: str) -> None:
    active_scraping_tasks[user.username] += 1
    logger.info("Task %s registered for %s (user: %d, total: %d)",
                task_id, user.username, active_scraping_tasks[user.username], sum(active_scraping_tasks.values()))


def unregister_task(username: str, task_id: str) -> None:
    if active_scraping_tasks[username] > 0:
        active_scraping_tasks[username] -= 1
    logger.info("Task %s unregistered for %s", task_id, username)


def force_cleanup_user(username: str) -> int:
    count = active_scraping_tasks[username]
    active_scraping_tasks[username] = 0
    logger.info("Force cleaned %d tasks for %s", count, username)
    return count


def cancel_all() -> int:
    total = sum(active_scraping_tasks.values())
    active_scraping_tasks.clear()
    logger.info("Cancelled all tasks: %d", total)
    return total


def get_active_summary() -> dict:
    sync_counters()
    return {
        "total_active_tasks": sum(active_scraping_tasks.values()),
        "max_global_limit": settings.MAX_CONCURRENT_TASKS_GLOBAL,
        "max_user_limit": settings.MAX_CONCURRENT_TASKS_PER_USER,
        "tasks_by_user": dict(active_scraping_tasks),
    }


# === Readiness ===

async def check_readiness(db: AsyncSession, username: str) -> dict:
    sync_counters()
    categories = await check_categories(db)
    user_tasks = active_scraping_tasks[username]
    total_tasks = sum(active_scraping_tasks.values())
    can_start = (
        categories["has_categories"]
        and user_tasks < settings.MAX_CONCURRENT_TASKS_PER_USER
        and total_tasks < settings.MAX_CONCURRENT_TASKS_GLOBAL
    )

    issues = []
    if not categories["has_categories"]:
        issues.append({"type": "no_categories", "message": "No active categories"})
    if user_tasks >= settings.MAX_CONCURRENT_TASKS_PER_USER:
        issues.append({"type": "user_limit", "message": f"User limit ({user_tasks}/{settings.MAX_CONCURRENT_TASKS_PER_USER})"})
    if total_tasks >= settings.MAX_CONCURRENT_TASKS_GLOBAL:
        issues.append({"type": "global_limit", "message": f"Global limit ({total_tasks}/{settings.MAX_CONCURRENT_TASKS_GLOBAL})"})

    return {
        "ready": can_start,
        "categories": categories,
        "limits": {
            "user_tasks": user_tasks,
            "max_user_tasks": settings.MAX_CONCURRENT_TASKS_PER_USER,
            "total_tasks": total_tasks,
            "max_total_tasks": settings.MAX_CONCURRENT_TASKS_GLOBAL,
            "can_start_task": can_start,
        },
        "issues": issues,
    }


# === URL validation ===

MAX_URLS_PER_TASK = 10


def validate_urls(urls: list[str], base_url: Optional[str] = None) -> list[str]:
    valid = [u.strip() for u in urls if u.strip()]
    if not valid:
        raise_400("No valid URLs provided")
    if len(valid) > MAX_URLS_PER_TASK:
        raise_400(f"Too many URLs (max {MAX_URLS_PER_TASK})")

    if base_url:
        return [
            u if u.startswith("http") else f"{base_url}{u}" if u.startswith("/") else f"{base_url}/{u}"
            for u in valid
        ]
    return valid


# === Start scraping ===

async def start_scrape(db: AsyncSession, user: AdminUser, scraper_type: ScraperType, urls: list[str]) -> dict:
    cfg = get_config(scraper_type)
    await require_categories(db)
    check_limits(user)
    valid_urls = validate_urls(urls, cfg.base_url)

    task = cfg.task.delay(valid_urls, user.username)
    register_task(user, task.id)
    logger.info("%s task %s started by %s (%d URLs)", cfg.name, task.id, user.username, len(valid_urls))

    return {
        "task_id": task.id,
        "message": f"{cfg.name} scraping started ({len(valid_urls)} URLs)",
        "initiated_by": user.username,
        "urls_count": len(valid_urls),
    }


# === Task status ===

def get_task_status(task_id: str, username: str) -> dict:
    from celery.result import AsyncResult
    result = AsyncResult(task_id)
    response: dict[str, Any] = {"task_id": task_id, "status": result.status}

    if hasattr(result, "info") and isinstance(result.info, dict) and "progress" in result.info:
        response["progress"] = result.info["progress"]

    if result.ready():
        if result.successful():
            response["status"] = "SUCCESS"
            response["result"] = result.result
        else:
            response["status"] = "FAILURE"
            response["error"] = str(result.result)
        unregister_task(username, task_id)

    return response