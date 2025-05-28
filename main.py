import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.v1.products import router as products_router
from app.api.v1.categories import router as categories_router
from app.api.v1.catalogs import router as catalogs_router
from app.api.v1.import_logs import router as import_logs_router
from app.api.v1.scraper import router as scraper_router
from app.api.v1.video import router as video_router
from app.api.v1.brand import router as brand_router
# Test auto-deploy
app = FastAPI()

app.include_router(products_router, prefix="/api/v1/products", tags=["Products"])
app.include_router(categories_router, prefix="/api/v1/categories", tags=["Categories"])
app.include_router(catalogs_router, prefix="/api/v1/catalogs", tags=["Catalogs"])
app.include_router(import_logs_router, prefix="/api/v1/import-logs", tags=["Import Logs"])
app.include_router(scraper_router, prefix="/api/v1/scraper", tags=["Scrapers"])
app.include_router(video_router, prefix="/api/v1/video", tags=["Video"])
app.include_router(brand_router, prefix="/api/v1/brand", tags=["Brand"])

os.makedirs("media", exist_ok=True)
app.mount("/media", StaticFiles(directory="media"), name="media")

@app.get("/")
def root():
    return {"message": "It works!"}
