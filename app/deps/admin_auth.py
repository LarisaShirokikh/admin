# app/deps/admin_auth.py
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
import jwt
from datetime import datetime

from app.deps import get_db
from app.crud.admin import admin_user
from app.models.admin import AdminUser

# Используем тот же секрет что и в роутах (потом вынесем в настройки)
JWT_SECRET = "your-temp-secret-key-change-this"
ALGORITHM = "HS256"

security = HTTPBearer()

class AdminAuthException(HTTPException):
    def __init__(self, detail: str = "Not authenticated"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

class AdminPermissionException(HTTPException):
    def __init__(self, detail: str = "Not enough permissions"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )

async def get_current_admin_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> AdminUser:
    token = credentials.credentials
    
    try:
        # Декодируем JWT токен
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
        token_type = payload.get("type")
        
        # Проверяем что это access токен
        if token_type != "access":
            raise AdminAuthException("Invalid token type")
        
        # Получаем пользователя из базы
        user = await admin_user.get(db, user_id)
        if not user:
            raise AdminAuthException("User not found")
        
        # Проверяем активность пользователя
        if not admin_user.is_active(user):
            raise AdminAuthException("Inactive user")
        
        # Проверяем блокировку
        if admin_user.is_locked(user):
            raise AdminAuthException("Account is locked")
        
        return user
        
    except jwt.ExpiredSignatureError:
        raise AdminAuthException("Token expired")
    except jwt.InvalidTokenError:
        raise AdminAuthException("Invalid token")
    except ValueError:
        raise AdminAuthException("Invalid token format")
    except Exception as e:
        raise AdminAuthException(f"Authentication error: {str(e)}")

async def get_current_active_admin(
    current_user: AdminUser = Depends(get_current_admin_user)
) -> AdminUser:
    if not admin_user.is_active(current_user):
        raise AdminAuthException("Inactive user")
    return current_user

async def get_current_superuser(
    current_user: AdminUser = Depends(get_current_active_admin)
) -> AdminUser:
    if not admin_user.is_superuser(current_user):
        raise AdminPermissionException("Not enough permissions. Superuser required.")
    return current_user

admin_rate_limits = defaultdict(list)

def check_admin_rate_limit(request: Request, max_requests: int = 60, window_minutes: int = 1):
    """
    Простой rate limiter для админских запросов
    """
    client_ip = request.client.host
    now = datetime.utcnow()
    window_start = now - timedelta(minutes=window_minutes)
    
    # Очищаем старые записи
    admin_rate_limits[client_ip] = [
        timestamp for timestamp in admin_rate_limits[client_ip] 
        if timestamp > window_start
    ]
    
    # Проверяем лимит
    if len(admin_rate_limits[client_ip]) >= max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down."
        )
    
    # Добавляем текущий запрос
    admin_rate_limits[client_ip].append(now)