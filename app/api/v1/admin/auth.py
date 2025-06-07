# app/api/v1/admin/auth.py (или где у вас находится этот файл)
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
import secrets
import jwt

from app.deps import get_db
from app.crud.admin import admin_user
from app.schemas.admin import AdminLoginRequest, AdminLoginResponse

router = APIRouter()

# Временный секрет для JWT (потом перенесем в .env)
JWT_SECRET = "your-temp-secret-key-change-this"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 5

def create_access_token(user_id: int) -> tuple[str, str]:
    """Создание access и refresh токенов"""
    # Access token с коротким сроком жизни
    access_payload = {
        "sub": str(user_id),
        "type": "access",
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    }
    access_token = jwt.encode(access_payload, JWT_SECRET, algorithm=ALGORITHM)
    
    # Refresh token с длинным сроком
    refresh_payload = {
        "sub": str(user_id),
        "type": "refresh", 
        "exp": datetime.utcnow() + timedelta(hours=24)
    }
    refresh_token = jwt.encode(refresh_payload, JWT_SECRET, algorithm=ALGORITHM)
    
    return access_token, refresh_token

@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(
    request: Request,
    login_data: AdminLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Авторизация админа
    """
    # Аутентификация (ВАЖНО: добавляем await!)
    user = await admin_user.authenticate(db, login_data.username, login_data.password)
    if not user:
        # Увеличиваем счетчик неудачных попыток если пользователь существует
        failed_user = await admin_user.get_by_username(db, login_data.username)
        if failed_user:
            await admin_user.increment_failed_login(db, failed_user)
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    # Проверяем активность
    if not admin_user.is_active(user):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user"
        )
    
    # Проверяем блокировку
    if admin_user.is_locked(user):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is locked due to multiple failed login attempts"
        )
    
    # Создаем токены
    access_token, refresh_token = create_access_token(user.id)
    
    # Обновляем время последнего входа (ВАЖНО: добавляем await!)
    await admin_user.update_last_login(db, user)
    
    return AdminLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # в секундах
        user=user
    )

@router.post("/refresh")
async def refresh_token(
    request: Request,
    refresh_token: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Обновление access токена
    """
    try:
        payload = jwt.decode(refresh_token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
        token_type = payload.get("type")
        
        if token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired"
        )
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    # Проверяем что пользователь существует и активен (ВАЖНО: добавляем await!)
    user = await admin_user.get(db, user_id)
    if not user or not admin_user.is_active(user):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    # Создаем новые токены
    new_access_token, new_refresh_token = create_access_token(user.id)
    
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }

@router.post("/logout")
async def admin_logout():
    """
    Выход из админки (пока просто заглушка)
    """
    return {"message": "Successfully logged out"}

@router.get("/test")
async def test_endpoint():
    """
    Тестовый endpoint для проверки работы роутов
    """
    return {"message": "Admin routes working!", "timestamp": datetime.utcnow()}