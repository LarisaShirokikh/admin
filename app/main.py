import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.crud import admin as admin_crud

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSessionLocal() as db:
        existing = await admin_crud.get_by_username(db, settings.ADMIN_USERNAME)
        if not existing:
            from app.schemas.admin import AdminUserCreate
            await admin_crud.create(db, AdminUserCreate(
                username=settings.ADMIN_USERNAME,
                email=settings.ADMIN_EMAIL,
                password=settings.ADMIN_PASSWORD,
                confirm_password=settings.ADMIN_PASSWORD,
                is_superuser=True,
            ))
            logger.info("Superadmin created: %s", settings.ADMIN_USERNAME)
    yield


app = FastAPI(
    title="Doors API",
    description="API for dverin.pro",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "https://dverin.pro",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    max_age=settings.SESSION_EXPIRE_HOURS * 3600,
)

app.include_router(api_router)

os.makedirs("media", exist_ok=True)
app.mount("/media", StaticFiles(directory="media"), name="media")


@app.get("/")
def root():
    return {"message": "Doors API v2.0"}
