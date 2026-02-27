# app/schemas/auth.py
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, EmailStr, Field


# === Схемы для Yandex OAuth ===

class YandexUserInfo(BaseModel):
    """Информация о пользователе от Yandex"""
    id: str
    login: str
    default_email: EmailStr
    display_name: Optional[str] = None
    real_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    sex: Optional[str] = None
    default_avatar_id: Optional[str] = None
    is_avatar_empty: bool = True
    birthday: Optional[str] = None
    psuid: Optional[str] = None


class OAuthCallbackData(BaseModel):
    code: str
    state: Optional[str] = None


# === Схемы для авторизации ===

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    is_active: bool = True
    is_admin: bool = False
    is_superuser: bool = False
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class CurrentUser(UserResponse):
    yandex_id: Optional[str] = None
    oauth_provider: Optional[str] = None


class AuthStatus(BaseModel):
    is_authenticated: bool
    user: Optional[UserResponse] = None


class LoginResponse(BaseModel):
    """Ответ при успешной авторизации"""
    message: str
    user: UserResponse


class LogoutResponse(BaseModel):
    """Ответ при выходе"""
    message: str = "Successfully logged out"

# === Схемы для создания/обновления пользователей ===

class UserCreate(BaseModel):
    """Схема для создания пользователя"""
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    yandex_id: Optional[str] = None
    oauth_provider: Optional[str] = None
    oauth_data: Optional[Dict[str, Any]] = None
    is_admin: bool = False
    is_superuser: bool = False


class UserUpdate(BaseModel):
    """Схема для обновления пользователя"""
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    is_superuser: Optional[bool] = None

# === Схемы для сессий ===

class SessionCreate(BaseModel):
    """Схема для создания сессии"""
    user_id: int
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    device_info: Optional[Dict[str, Any]] = None
    expires_in: int = 3600  # Время жизни в секундах (по умолчанию 1 час)