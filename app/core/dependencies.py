from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
import jwt

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.exceptions import raise_401, raise_403, raise_429
from app.crud import admin as admin_crud
from app.models.admin import AdminUser

security = HTTPBearer()


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_current_admin_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.ALGORITHM])
        user_id = int(payload.get("sub"))
        if payload.get("type") != "access":
            raise_401("Invalid token type")

        user = await admin_crud.get(db, user_id)
        if not user:
            raise_401("User not found")
        if not admin_crud.is_active(user):
            raise_401("Inactive user")
        if admin_crud.is_locked(user):
            raise_401("Account is locked")
        return user

    except jwt.ExpiredSignatureError:
        raise_401("Token expired")
    except jwt.InvalidTokenError:
        raise_401("Invalid token")
    except ValueError:
        raise_401("Invalid token format")


async def get_current_active_admin(
    current_user: AdminUser = Depends(get_current_admin_user),
) -> AdminUser:
    if not admin_crud.is_active(current_user):
        raise_401("Inactive user")
    return current_user


async def get_current_superuser(
    current_user: AdminUser = Depends(get_current_active_admin),
) -> AdminUser:
    if not admin_crud.is_superuser(current_user):
        raise_403("Superuser required")
    return current_user


_rate_limits: dict = defaultdict(list)


def check_admin_rate_limit(
    request: Request, max_requests: int = 60, window_minutes: int = 1
):
    client_ip = f"{request.client.host}:{request.url.path}"
    now = datetime.utcnow()
    window_start = now - timedelta(minutes=window_minutes)

    _rate_limits[client_ip] = [
        ts for ts in _rate_limits[client_ip] if ts > window_start
    ]
    if len(_rate_limits[client_ip]) >= max_requests:
        raise_429()
    _rate_limits[client_ip].append(now)
