import os
import time
from fastapi import FastAPI, HTTPException, Request
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.products import router as products_router
from app.api.v1.categories import router as categories_router
from app.api.v1.catalogs import router as catalogs_router
from app.api.v1.import_logs import router as import_logs_router
from app.api.v1.scraper import router as scraper_router
from app.api.v1.video import router as video_router
from app.api.v1.brands import router as brand_router
from app.api.v1.admin.auth import router as admin_auth_router
from app.api.v1.posts import router as posts_router
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
app.include_router(brand_router, prefix="/api/v1/brands", tags=["Brand"])
app.include_router(admin_auth_router, prefix="/api/v1/admin/auth", tags=["Auth"])
app.include_router(posts_router, prefix="/posts", tags=["posts"])



os.makedirs("media", exist_ok=True)
app.mount("/media", StaticFiles(directory="media"), name="media")

@app.get("/")
def root():
    return {"message": "It works admin-api!"}

@app.get("/debug/media")
async def debug_media_files():
    """Диагностика медиа файлов"""
    
    # Проверяем рабочую директорию
    current_dir = os.getcwd()
    
    # Проверяем существование папок
    media_exists = os.path.exists("media")
    videos_exists = os.path.exists("media/videos")
    
    # Список файлов
    files_in_media = []
    files_in_videos = []
    
    if media_exists:
        files_in_media = os.listdir("media")
    
    if videos_exists:
        files_in_videos = os.listdir("media/videos")
    
    # Проверяем конкретный файл
    target_file = "media/videos/92a7ab1a-cea5-4f7b-8fe0-ce010a4e2495_IMG_6995.mp4"
    target_file_exists = os.path.exists(target_file)
    
    # Получаем абсолютные пути
    abs_media_path = os.path.abspath("media")
    abs_target_path = os.path.abspath(target_file)
    
    return {
        "current_directory": current_dir,
        "media_exists": media_exists,
        "videos_exists": videos_exists,
        "files_in_media": files_in_media,
        "files_in_videos": files_in_videos,
        "target_file_exists": target_file_exists,
        "absolute_media_path": abs_media_path,
        "absolute_target_path": abs_target_path,
        "target_file_path": target_file
    }

@app.get("/debug/file/{filename}")
async def debug_specific_file(filename: str):
    """Проверка конкретного файла"""
    file_path = f"media/videos/{filename}"
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
    
    file_stats = os.stat(file_path)
    
    return {
        "file_path": file_path,
        "absolute_path": os.path.abspath(file_path),
        "file_size": file_stats.st_size,
        "exists": True
    }