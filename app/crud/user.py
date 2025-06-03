# app/crud/user.py
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload

from app.models.user import User, UserSession
from app.schemas.auth import SessionCreate, UserCreate, UserUpdate, YandexUserInfo



class UserCRUD:
    """CRUD операции для пользователей"""
    
    async def get_by_id(self, db: AsyncSession, user_id: int) -> Optional[User]:
        """Получить пользователя по ID"""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()
    
    async def get_by_uuid(self, db: AsyncSession, user_uuid: str) -> Optional[User]:
        """Получить пользователя по UUID"""
        result = await db.execute(select(User).where(User.uuid == user_uuid))
        return result.scalar_one_or_none()
    
    async def get_by_email(self, db: AsyncSession, email: str) -> Optional[User]:
        """Получить пользователя по email"""
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()
    
    async def get_by_yandex_id(self, db: AsyncSession, yandex_id: str) -> Optional[User]:
        """Получить пользователя по Yandex ID"""
        result = await db.execute(select(User).where(User.yandex_id == yandex_id))
        return result.scalar_one_or_none()
    
    async def create(self, db: AsyncSession, user_create: UserCreate) -> User:
        """Создать нового пользователя"""
        user = User(**user_create.model_dump())
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user
    
    async def create_from_yandex(
        self, 
        db: AsyncSession, 
        yandex_user: YandexUserInfo,
        oauth_data: Dict[str, Any]
    ) -> User:
        """Создать пользователя из данных Яндекса"""
        
        # Формируем полное имя
        full_name = yandex_user.display_name or yandex_user.real_name
        if not full_name and yandex_user.first_name:
            full_name = f"{yandex_user.first_name} {yandex_user.last_name or ''}".strip()
        
        # Генерируем URL аватара
        avatar_url = None
        if yandex_user.default_avatar_id and not yandex_user.is_avatar_empty:
            avatar_url = f"https://avatars.yandex.net/get-yapic/{yandex_user.default_avatar_id}/islands-200"
        
        # Создаем пользователя
        user_data = UserCreate(
            email=yandex_user.default_email,
            full_name=full_name,
            avatar_url=avatar_url,
            yandex_id=yandex_user.id,
            oauth_provider="yandex",
            oauth_data=oauth_data
        )
        
        return await self.create(db, user_data)
    
    async def update(self, db: AsyncSession, user: User, user_update: UserUpdate) -> User:
        """Обновить пользователя"""
        update_data = user_update.model_dump(exclude_unset=True)
        
        for field, value in update_data.items():
            setattr(user, field, value)
        
        user.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(user)
        return user
    
    async def update_last_login(self, db: AsyncSession, user: User) -> User:
        """Обновить время последнего входа"""
        user.last_login_at = datetime.utcnow()
        await db.commit()
        await db.refresh(user)
        return user
    
    async def deactivate(self, db: AsyncSession, user: User) -> User:
        """Деактивировать пользователя"""
        user.is_active = False
        user.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(user)
        return user

class SessionCRUD:
    """CRUD операции для сессий"""
    
    async def create(self, db: AsyncSession, session_create: SessionCreate) -> UserSession:
        """Создать новую сессию"""
        # Генерируем токены
        session_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)
        
        # Вычисляем время истечения
        expires_at = datetime.utcnow() + timedelta(seconds=session_create.expires_in)
        
        session = UserSession(
            user_id=session_create.user_id,
            session_token=session_token,
            refresh_token=refresh_token,
            ip_address=session_create.ip_address,
            user_agent=session_create.user_agent,
            device_info=session_create.device_info,
            expires_at=expires_at
        )
        
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session
    
    async def get_by_token(self, db: AsyncSession, session_token: str) -> Optional[UserSession]:
        """Получить сессию по токену"""
        result = await db.execute(
            select(UserSession).where(
                UserSession.session_token == session_token,
                UserSession.is_active == True,
                UserSession.expires_at > datetime.utcnow()
            )
        )
        return result.scalar_one_or_none()
    
    async def get_by_refresh_token(self, db: AsyncSession, refresh_token: str) -> Optional[UserSession]:
        """Получить сессию по refresh токену"""
        result = await db.execute(
            select(UserSession).where(
                UserSession.refresh_token == refresh_token,
                UserSession.is_active == True
            )
        )
        return result.scalar_one_or_none()
    
    async def update_last_used(self, db: AsyncSession, session: UserSession) -> UserSession:
        """Обновить время последнего использования"""
        session.last_used_at = datetime.utcnow()
        await db.commit()
        await db.refresh(session)
        return session
    
    async def refresh_session(self, db: AsyncSession, session: UserSession, expires_in: int = 3600) -> UserSession:
        """Обновить сессию (продлить время действия)"""
        # Генерируем новые токены
        session.session_token = secrets.token_urlsafe(32)
        session.refresh_token = secrets.token_urlsafe(32)
        session.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        session.last_used_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(session)
        return session
    
    async def deactivate(self, db: AsyncSession, session: UserSession) -> UserSession:
        """Деактивировать сессию"""
        session.is_active = False
        await db.commit()
        await db.refresh(session)
        return session
    
    async def deactivate_user_sessions(self, db: AsyncSession, user_id: int) -> None:
        """Деактивировать все сессии пользователя"""
        await db.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id)
            .values(is_active=False)
        )
        await db.commit()
    
    async def cleanup_expired_sessions(self, db: AsyncSession) -> int:
        """Удалить истекшие сессии"""
        result = await db.execute(
            delete(UserSession).where(
                UserSession.expires_at < datetime.utcnow(),
                UserSession.is_active == False
            )
        )
        await db.commit()
        return result.rowcount

# Создаем экземпляры CRUD
user_crud = UserCRUD()
session_crud = SessionCRUD()