from collections import defaultdict
from typing import Dict

active_scraping_tasks: Dict[str, int] = defaultdict(int)

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str
    redis_url: str

    # Security
    SECRET_KEY: str
    JWT_SECRET: str = "your-temp-secret-key-change-this"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_HOURS: int = 168

    # Session
    SESSION_EXPIRE_HOURS: int = 24

    # Default superadmin
    ADMIN_USERNAME: str = "dverin"
    ADMIN_EMAIL: str = "admin@dverin.pro"
    ADMIN_PASSWORD: str = "dverin"

    # Scraping limits
    MAX_CONCURRENT_TASKS_PER_USER: int = 2
    MAX_CONCURRENT_TASKS_GLOBAL: int = 5

    UPLOAD_DIR: str = "/app/media"
    ALLOWED_IMAGE_EXTENSIONS: list = [".png", ".jpg", ".jpeg", ".gif", ".webp"]
    MAX_IMAGE_SIZE: int = 10 * 1024 * 1024

    # Video
    ALLOWED_VIDEO_EXTENSIONS: list = [".mp4", ".mov", ".avi", ".mkv", ".webm"]
    MAX_VIDEO_SIZE: int = 100 * 1024 * 1024  # 100MB
    MAX_UPLOADS_PER_USER: int = 5
    MAX_UPLOADS_GLOBAL: int = 20


settings = Settings()

