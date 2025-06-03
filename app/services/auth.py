# app/services/auth.py
import secrets
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from fastapi import HTTPException, status, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.user import user_crud
from app.models.user import User, UserSession
from app.schemas.auth import YandexUserInfo, SessionCreate, UserCreate

from app.crud.user import user_crud, session_crud
from app.core.config import Settings
from app.services.oauth import YandexOAuthClient


class AuthService:
    """Сервис авторизации"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.oauth_client = YandexOAuthClient(settings)
    
    def get_authorization_url(self, state: str) -> str:
        """Получить URL для авторизации"""
        return self.oauth_client.get_authorization_url(state)
    
    async def process_oauth_callback(
        self,
        code: str,
        state: str,
        request: Request,
        db: AsyncSession
    ) -> Tuple[User, UserSession]:
        """Обработать callback от OAuth провайдера"""
        
        # Обмениваем код на токен
        token_data = await self.oauth_client.exchange_code_for_token(code)
        access_token = token_data.get("access_token")
        
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to obtain access token"
            )
        
        # Получаем информацию о пользователе
        yandex_user = await self.oauth_client.get_user_info(access_token)
        
        # Ищем существующего пользователя
        user = await user_crud.get_by_yandex_id(db, yandex_user.id)
        
        if not user:
            # Проверяем, есть ли пользователь с таким email
            existing_user = await user_crud.get_by_email(db, yandex_user.default_email)
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User with this email already exists"
                )
            
            # Создаем нового пользователя
            user = await user_crud.create_from_yandex(db, yandex_user, token_data)
            
            # Проверяем, нужно ли дать админские права
            if yandex_user.id in self.settings.DEFAULT_ADMIN_YANDEX_IDS:
                user.is_admin = True
                user.is_superuser = True
                await db.commit()
                await db.refresh(user)
        
        else:
            # Обновляем время последнего входа
            await user_crud.update_last_login(db, user)
        
        # Создаем сессию
        session_data = SessionCreate(
            user_id=user.id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
            device_info=self._extract_device_info(request),
            expires_in=self.settings.SESSION_EXPIRE_HOURS * 3600
        )
        
        session = await session_crud.create(db, session_data)
        
        return user, session
    
    async def logout(
        self,
        session: UserSession,
        db: AsyncSession
    ) -> None:
        """Выйти из системы"""
        await session_crud.deactivate(db, session)
    
    async def logout_all(
        self,
        user_id: int,
        db: AsyncSession
    ) -> None:
        """Выйти из всех сессий"""
        await session_crud.deactivate_user_sessions(db, user_id)
    
    def set_session_cookies(
        self,
        response: Response,
        session: UserSession,
        secure: bool = False
    ) -> None:
        """Установить cookies для сессии"""
        expires_delta = session.expires_at - datetime.utcnow()
        max_age = int(expires_delta.total_seconds())
        
        response.set_cookie(
            key="session_token",
            value=session.session_token,
            max_age=max_age,
            httponly=True,
            secure=secure,
            samesite="lax"
        )
    
    def clear_session_cookies(self, response: Response) -> None:
        """Очистить cookies сессии"""
        response.delete_cookie(key="session_token", httponly=True)
    
    def generate_state_token(self) -> str:
        """Генерировать state токен для OAuth"""
        return secrets.token_urlsafe(32)
    
    def _extract_device_info(self, request: Request) -> Dict[str, Any]:
        """Извлечь информацию об устройстве из запроса"""
        user_agent = request.headers.get("User-Agent", "")
        
        return {
            "user_agent": user_agent,
            "accept_language": request.headers.get("Accept-Language"),
            "accept_encoding": request.headers.get("Accept-Encoding"),
            "connection": request.headers.get("Connection"),
            "upgrade_insecure_requests": request.headers.get("Upgrade-Insecure-Requests")
        }