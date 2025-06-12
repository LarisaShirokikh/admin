# app/api/v1/admin/auth.py (исправленный)
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from pydantic import BaseModel
import jwt

from app.deps import get_db
from app.crud.admin import admin_user
from app.deps.admin_auth import get_current_active_admin
from app.models.admin import AdminUser
from app.schemas.admin import AdminLoginRequest, AdminLoginResponse

router = APIRouter()

# Временный секрет для JWT (потом перенесем в .env)
JWT_SECRET = "your-temp-secret-key-change-this"
ALGORITHM = "HS256"

# ИСПРАВЛЕНО: Увеличиваем время жизни токенов
ACCESS_TOKEN_EXPIRE_MINUTES = 120  # 2 часа вместо 5 минут
REFRESH_TOKEN_EXPIRE_HOURS = 24 * 7  # 7 дней

# Схема для refresh токена
class RefreshTokenRequest(BaseModel):
    refresh_token: str

def create_access_token(user_id: int) -> tuple[str, str]:
    """Создание access и refresh токенов"""
    # Access token с увеличенным сроком жизни
    access_payload = {
        "sub": str(user_id),
        "type": "access",
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": datetime.utcnow()  # Добавляем время создания
    }
    access_token = jwt.encode(access_payload, JWT_SECRET, algorithm=ALGORITHM)
    
    # Refresh token с длинным сроком
    refresh_payload = {
        "sub": str(user_id),
        "type": "refresh", 
        "exp": datetime.utcnow() + timedelta(hours=REFRESH_TOKEN_EXPIRE_HOURS),
        "iat": datetime.utcnow()
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
    print(f"Login attempt for user: {login_data.username}")
    
    # Аутентификация
    user = await admin_user.authenticate(db, login_data.username, login_data.password)
    if not user:
        print(f"Authentication failed for user: {login_data.username}")
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
        print(f"User {login_data.username} is inactive")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user"
        )
    
    # Проверяем блокировку
    if admin_user.is_locked(user):
        print(f"User {login_data.username} is locked")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is locked due to multiple failed login attempts"
        )
    
    # Создаем токены
    access_token, refresh_token = create_access_token(user.id)
    
    # Обновляем время последнего входа
    await admin_user.update_last_login(db, user)
    
    print(f"User {login_data.username} logged in successfully")
    
    return AdminLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # в секундах
        user=user
    )

@router.post("/refresh")
async def refresh_token(
    request: Request,
    token_data: RefreshTokenRequest,  # ИСПРАВЛЕНО: используем Pydantic модель
    db: AsyncSession = Depends(get_db)
):
    """
    Обновление access токена
    """
    print("Refresh token request received")
    
    try:
        payload = jwt.decode(token_data.refresh_token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
        token_type = payload.get("type")
        
        if token_type != "refresh":
            print("Invalid token type")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        print(f"Refreshing token for user_id: {user_id}")
        
    except jwt.ExpiredSignatureError:
        print("Refresh token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired"
        )
    except (jwt.InvalidTokenError, ValueError) as e:
        print(f"Invalid refresh token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    # Проверяем что пользователь существует и активен
    user = await admin_user.get(db, user_id)
    if not user or not admin_user.is_active(user):
        print(f"User {user_id} not found or inactive")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    # Создаем новые токены
    new_access_token, new_refresh_token = create_access_token(user.id)
    
    print(f"New tokens created for user {user_id}")
    
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }

@router.get("/me")
async def get_current_user(
    request: Request,
    current_user: AdminUser = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Получить информацию о текущем авторизованном пользователе
    """
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "is_active": current_user.is_active,
        "is_superuser": current_user.is_superuser,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        "last_login": current_user.last_login.isoformat() if current_user.last_login else None,
        "failed_login_attempts": current_user.failed_login_attempts,
        "locked_until": current_user.locked_until.isoformat() if current_user.locked_until else None
    }

@router.post("/logout")
async def admin_logout():
    """
    Выход из админки
    """
    print("User logout")
    return {"message": "Successfully logged out"}

@router.get("/test")
async def test_endpoint():
    """
    Тестовый endpoint для проверки работы роутов
    """
    return {
        "message": "Admin routes working!", 
        "timestamp": datetime.utcnow(),
        "token_config": {
            "access_token_expire_minutes": ACCESS_TOKEN_EXPIRE_MINUTES,
            "refresh_token_expire_hours": REFRESH_TOKEN_EXPIRE_HOURS
        }
    }