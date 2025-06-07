import os
import time
from fastapi import FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.products import router as products_router
from app.api.v1.categories import router as categories_router
from app.api.v1.catalogs import router as catalogs_router
from app.api.v1.import_logs import router as import_logs_router
from app.api.v1.scraper import router as scraper_router
from app.api.v1.video import router as video_router
from app.api.v1.brand import router as brand_router
from app.api.v1.admin.auth import router as admin_auth_router
from app.core.config import Settings

app = FastAPI(
    title="Admin API",
    root_path="/admin-api",
    description="API для управления каталогом дверей",
    version="1.0.0"
)

settings = Settings()

@app.middleware("http")
async def log_all_auth_requests(request: Request, call_next):
    """Логировать все auth запросы"""
    
    # Логируем только auth запросы
    if "/auth/" in str(request.url):
        current_time = time.time()
        print(f"\n🌐 REQUEST LOG #{int(current_time)}:")
        print(f"   Method: {request.method}")
        print(f"   URL: {request.url}")
        print(f"   Client: {request.client.host if request.client else 'Unknown'}:{request.client.port if request.client else 'Unknown'}")
        print(f"   User-Agent: {request.headers.get('User-Agent', 'None')[:100]}")
        print(f"   Referer: {request.headers.get('Referer', 'None')}")
        print(f"   Sec-Fetch-Site: {request.headers.get('Sec-Fetch-Site', 'None')}")
        print(f"   Sec-Fetch-Mode: {request.headers.get('Sec-Fetch-Mode', 'None')}")
        print(f"   Origin: {request.headers.get('Origin', 'None')}")
        
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        
        print(f"   Response: {response.status_code} (took {process_time:.3f}s)")
        print("")
        
        return response
    
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://172.22.0.2:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
app.include_router(admin_auth_router, prefix="/api/v1/admin-api/auth", tags=["Admin-auth"])


os.makedirs("media", exist_ok=True)
app.mount("/media", StaticFiles(directory="media"), name="media")

@app.get("/")
def root():
    return {"message": "It works admin-api!"}

