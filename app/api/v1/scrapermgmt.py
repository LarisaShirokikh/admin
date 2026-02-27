from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import scraper as scraper_crud
from app.core.dependencies import get_db, get_current_active_admin, get_current_superuser, check_admin_rate_limit
from app.models.admin import AdminUser
from app.schemas.scraper import ScraperType, ScraperRequest, ScraperResponse, ScraperStatus

router = APIRouter()


@router.post("/scrape-labirint", response_model=ScraperResponse)
async def scrape_labirint(
    request: Request,
    body: ScraperRequest,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=10, window_minutes=10)
    return await scraper_crud.start_scrape(db, current_user, ScraperType.LABIRINT, body.catalog_urls)


@router.post("/scrape-bunker", response_model=ScraperResponse)
async def scrape_bunker(
    request: Request,
    body: ScraperRequest,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=10, window_minutes=10)
    return await scraper_crud.start_scrape(db, current_user, ScraperType.BUNKER, body.catalog_urls)


@router.post("/scrape-intecron", response_model=ScraperResponse)
async def scrape_intecron(
    request: Request,
    body: ScraperRequest,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=10, window_minutes=10)
    return await scraper_crud.start_scrape(db, current_user, ScraperType.INTECRON, body.catalog_urls)


@router.post("/scrape-as-doors", response_model=ScraperResponse)
async def scrape_as_doors(
    request: Request,
    body: ScraperRequest,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    check_admin_rate_limit(request, max_requests=10, window_minutes=10)
    return await scraper_crud.start_scrape(db, current_user, ScraperType.AS_DOORS, body.catalog_urls)


# === Monitoring ===

@router.get("/scraper-status/{task_id}", response_model=ScraperStatus)
async def get_scraper_status(
    request: Request,
    task_id: str,
    current_user: AdminUser = Depends(get_current_active_admin),
):
    check_admin_rate_limit(request, max_requests=60, window_minutes=1)
    return scraper_crud.get_task_status(task_id, current_user.username)


@router.get("/check-readiness")
async def check_readiness(
    request: Request,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    return await scraper_crud.check_readiness(db, current_user.username)


@router.get("/active-tasks")
async def get_active_tasks(
    request: Request,
    current_user: AdminUser = Depends(get_current_superuser),
):
    return scraper_crud.get_active_summary()


# === Actions ===

@router.post("/sync-tasks")
async def sync_tasks(
    request: Request,
    current_user: AdminUser = Depends(get_current_active_admin),
):
    check_admin_rate_limit(request, max_requests=10, window_minutes=1)
    return scraper_crud.sync_counters()


@router.post("/cleanup-my-tasks")
async def cleanup_my_tasks(
    request: Request,
    current_user: AdminUser = Depends(get_current_active_admin),
):
    check_admin_rate_limit(request, max_requests=5, window_minutes=5)
    cleaned = scraper_crud.force_cleanup_user(current_user.username)
    return {"message": f"Cleaned {cleaned} tasks", "cleaned_tasks": cleaned}


@router.post("/cancel-all-tasks")
async def cancel_all_tasks(
    request: Request,
    current_user: AdminUser = Depends(get_current_superuser),
):
    cancelled = scraper_crud.cancel_all()
    return {"message": f"Cancelled {cancelled} tasks", "cancelled_tasks": cancelled, "cancelled_by": current_user.username}