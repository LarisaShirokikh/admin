from datetime import datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_db, get_current_active_admin, get_current_superuser
from app.core.exceptions import raise_401
from app.crud import admin as admin_crud
from app.models.admin import AdminUser
from app.schemas.admin import AdminLoginRequest, AdminLoginResponse

router = APIRouter()


class RefreshTokenRequest(BaseModel):
    refresh_token: str


def create_tokens(user_id: int) -> tuple[str, str]:
    now = datetime.utcnow()
    access = jwt.encode(
        {"sub": str(user_id), "type": "access", "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES), "iat": now},
        settings.JWT_SECRET, algorithm=settings.ALGORITHM,
    )
    refresh = jwt.encode(
        {"sub": str(user_id), "type": "refresh", "exp": now + timedelta(hours=settings.REFRESH_TOKEN_EXPIRE_HOURS), "iat": now},
        settings.JWT_SECRET, algorithm=settings.ALGORITHM,
    )
    return access, refresh


@router.post("/login", response_model=AdminLoginResponse)
async def login(
    request: Request,
    login_data: AdminLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await admin_crud.authenticate(db, login_data.username, login_data.password)

    if not user:
        failed_user = await admin_crud.get_by_username(db, login_data.username)
        if failed_user:
            await admin_crud.increment_failed_login(db, failed_user)
        raise_401("Incorrect username or password")

    if not admin_crud.is_active(user):
        raise_401("Inactive user")
    if admin_crud.is_locked(user):
        raise_401("Account is locked")

    access_token, refresh_token = create_tokens(user.id)
    await admin_crud.update_last_login(db, user)

    return AdminLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user,
    )


@router.post("/refresh")
async def refresh(
    token_data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = jwt.decode(token_data.refresh_token, settings.JWT_SECRET, algorithms=[settings.ALGORITHM])
        user_id = int(payload.get("sub"))
        if payload.get("type") != "refresh":
            raise_401("Invalid token type")
    except jwt.ExpiredSignatureError:
        raise_401("Token expired")
    except (jwt.InvalidTokenError, ValueError):
        raise_401("Invalid token")

    user = await admin_crud.get(db, user_id)
    if not user or not admin_crud.is_active(user):
        raise_401("User not found or inactive")

    access, refresh_tok = create_tokens(user.id)
    return {
        "access_token": access,
        "refresh_token": refresh_tok,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.get("/me")
async def me(current_user: AdminUser = Depends(get_current_active_admin)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "is_active": current_user.is_active,
        "is_superuser": current_user.is_superuser,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        "last_login": current_user.last_login.isoformat() if current_user.last_login else None,
    }


@router.get("/users")
async def list_users(
    current_user: AdminUser = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    users = await admin_crud.get_multi(db, limit=50)
    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "is_active": u.is_active,
            "is_superuser": u.is_superuser,
            "last_login": u.last_login,
        }
        for u in users
    ]


@router.post("/logout")
async def logout():
    return {"message": "ok"}
