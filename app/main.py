import os
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.v1.products import router as products_router
from app.api.v1.categories import router as categories_router
from app.api.v1.catalogs import router as catalogs_router
from app.api.v1.import_logs import router as import_logs_router
from app.api.v1.scraper import router as scraper_router
from app.api.v1.video import router as video_router
from app.api.v1.brand import router as brand_router
from app.api.v1.auth import router as auth_router
from app.core.config import Settings

app = FastAPI(
    title="Admin API",
    root_path="/admin-api",
    description="API для управления каталогом дверей",
    version="1.0.0"
)

settings = Settings()

# Добавьте middleware для сессий (после создания app = FastAPI(...)):
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,  # Убедитесь, что SECRET_KEY есть в config
    max_age=settings.SESSION_EXPIRE_HOURS * 3600 if hasattr(settings, 'SESSION_EXPIRE_HOURS') else 86400
)

app.include_router(products_router, prefix="/api/v1/products", tags=["Products"])
app.include_router(categories_router, prefix="/api/v1/categories", tags=["Categories"])
app.include_router(catalogs_router, prefix="/api/v1/catalogs", tags=["Catalogs"])
app.include_router(import_logs_router, prefix="/api/v1/import-logs", tags=["Import Logs"])
app.include_router(scraper_router, prefix="/api/v1/scraper", tags=["Scrapers"])
app.include_router(video_router, prefix="/api/v1/video", tags=["Video"])
app.include_router(brand_router, prefix="/api/v1/brand", tags=["Brand"])
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])

os.makedirs("media", exist_ok=True)
app.mount("/media", StaticFiles(directory="media"), name="media")

@app.get("/")
def root():
    return {"message": "It works!"}