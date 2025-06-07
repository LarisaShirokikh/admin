# app/api/v1/admin/protected.py
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.deps import get_db

from app.deps.admin_auth import check_admin_rate_limit, get_current_active_admin, get_current_admin_user, get_current_superuser
from app.models.admin import AdminUser
from app.crud.admin import admin_user

router = APIRouter()

@router.get("/profile")
async def get_admin_profile(
    current_user: AdminUser = Depends(get_current_active_admin)
):
    """
    Получение профиля текущего админа (защищенный роут)
    """
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "is_active": current_user.is_active,
        "is_superuser": current_user.is_superuser,
        "created_at": current_user.created_at,
        "last_login": current_user.last_login,
        "failed_login_attempts": current_user.failed_login_attempts
    }

@router.get("/dashboard")
async def admin_dashboard(
    request: Request,
    current_user: AdminUser = Depends(get_current_active_admin)
):
    """
    Админская панель - базовая информация
    """
    # Проверяем rate limit
    check_admin_rate_limit(request, max_requests=30, window_minutes=1)
    
    return {
        "message": f"Добро пожаловать в админку, {current_user.username}!",
        "user_info": {
            "id": current_user.id,
            "username": current_user.username,
            "role": "Суперадмин" if current_user.is_superuser else "Админ"
        },
        "server_time": datetime.utcnow(),
        "permissions": {
            "can_manage_users": current_user.is_superuser,
            "can_view_logs": True,
            "can_manage_content": True
        }
    }

@router.get("/users")
async def list_admin_users(
    request: Request,
    current_user: AdminUser = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db)
):
    """
    Список всех админов (только для суперадмина)
    """
    check_admin_rate_limit(request, max_requests=20, window_minutes=1)
    
    users = await admin_user.get_multi(db, limit=50)
    
    return {
        "total_users": len(users),
        "users": [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "last_login": user.last_login,
                "created_at": user.created_at
            }
            for user in users
        ],
        "requested_by": current_user.username,
        "timestamp": datetime.utcnow()
    }

@router.get("/test-auth-levels")
async def test_auth_levels(
    request: Request,
    current_user: AdminUser = Depends(get_current_admin_user)
):
    """
    Тестирование разных уровней доступа
    """
    return {
        "message": "Базовая аутентификация пройдена",
        "user": current_user.username,
        "auth_level": "basic_admin",
        "timestamp": datetime.utcnow()
    }

@router.get("/test-superuser")
async def test_superuser_access(
    request: Request,
    current_user: AdminUser = Depends(get_current_superuser)
):
    """
    Тест доступа только для суперадмина
    """
    return {
        "message": "Доступ к суперадминским функциям разрешен",
        "user": current_user.username,
        "auth_level": "superuser",
        "timestamp": datetime.utcnow(),
        "secret_data": "Это видят только суперадмины! 🔐"
    }

@router.post("/test-rate-limit")
async def test_rate_limit(
    request: Request,
    current_user: AdminUser = Depends(get_current_active_admin)
):
    """
    Тест rate limiting (лимит: 5 запросов в минуту)
    """
    check_admin_rate_limit(request, max_requests=5, window_minutes=1)
    
    return {
        "message": "Rate limit OK",
        "user": current_user.username,
        "ip": request.client.host,
        "timestamp": datetime.utcnow()
    }