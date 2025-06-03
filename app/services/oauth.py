# app/services/oauth.py
import httpx
from typing import Optional, Dict, Any
from urllib.parse import urlencode
from fastapi import HTTPException, status

from app.core.config import Settings
from app.schemas.auth import YandexUserInfo


class YandexOAuthClient:
    """Клиент для работы с Yandex OAuth"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client_id = settings.YANDEX_CLIENT_ID
        self.client_secret = settings.YANDEX_CLIENT_SECRET
        self.redirect_uri = settings.YANDEX_REDIRECT_URI
        self.auth_url = settings.YANDEX_AUTH_URL
        self.token_url = settings.YANDEX_TOKEN_URL
        self.user_info_url = settings.YANDEX_USER_INFO_URL
        self.scope = settings.YANDEX_SCOPE
    
    def get_authorization_url(self, state: str) -> str:
        """Получить URL для авторизации пользователя"""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scope,
            "state": state,
            "force_confirm": "yes"  # Принудительное подтверждение
        }
        
        return f"{self.auth_url}?{urlencode(params)}"
    
    async def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """Обменять код авторизации на токен доступа"""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.token_url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to exchange code for token: {e.response.text}"
                )
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"OAuth token exchange failed: {str(e)}"
                )
    
    async def get_user_info(self, access_token: str) -> YandexUserInfo:
        """Получить информацию о пользователе"""
        headers = {
            "Authorization": f"OAuth {access_token}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    self.user_info_url,
                    headers=headers
                )
                response.raise_for_status()
                user_data = response.json()
                
                # Валидируем и возвращаем данные пользователя
                return YandexUserInfo(**user_data)
                
            except httpx.HTTPStatusError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to get user info: {e.response.text}"
                )
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to fetch user info: {str(e)}"
                )
    
    async def revoke_token(self, access_token: str) -> bool:
        """Отозвать токен доступа"""
        # Yandex не предоставляет публичный endpoint для отзыва токенов
        # Поэтому просто возвращаем True
        # В реальном приложении можно сохранить токен в черный список
        return True