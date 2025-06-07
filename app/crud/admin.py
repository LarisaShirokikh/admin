# app/crud/admin.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List
from datetime import datetime, timedelta
from passlib.context import CryptContext

from app.models.admin import AdminUser
from app.schemas.admin import AdminUserCreate

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class CRUDAdminUser:
    async def get(self, db: AsyncSession, id: int) -> Optional[AdminUser]:
        """Получить админа по ID"""
        result = await db.execute(select(AdminUser).filter(AdminUser.id == id))
        return result.scalar_one_or_none()
    
    async def get_by_username(self, db: AsyncSession, username: str) -> Optional[AdminUser]:
        """Получить админа по username"""
        result = await db.execute(select(AdminUser).filter(AdminUser.username == username))
        return result.scalar_one_or_none()
    
    async def get_by_email(self, db: AsyncSession, email: str) -> Optional[AdminUser]:
        """Получить админа по email"""
        result = await db.execute(select(AdminUser).filter(AdminUser.email == email))
        return result.scalar_one_or_none()
    
    async def get_multi(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> List[AdminUser]:
        """Получить список админов"""
        result = await db.execute(select(AdminUser).offset(skip).limit(limit))
        return result.scalars().all()
    
    async def create(self, db: AsyncSession, obj_in: AdminUserCreate) -> AdminUser:
        """Создать нового админа"""
        hashed_password = pwd_context.hash(obj_in.password)
        db_obj = AdminUser(
            username=obj_in.username,
            email=obj_in.email,
            hashed_password=hashed_password,
            is_active=obj_in.is_active,
            is_superuser=obj_in.is_superuser
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj
    
    async def authenticate(self, db: AsyncSession, username: str, password: str) -> Optional[AdminUser]:
        """Аутентификация админа"""
        user = await self.get_by_username(db, username=username)
        if not user:
            return None
        if not pwd_context.verify(password, user.hashed_password):
            return None
        return user
    
    def is_active(self, user: AdminUser) -> bool:
        """Проверка активности админа"""
        return user.is_active
    
    def is_superuser(self, user: AdminUser) -> bool:
        """Проверка прав суперадмина"""
        return user.is_superuser
    
    async def update_last_login(self, db: AsyncSession, user: AdminUser):
        """Обновить время последнего входа"""
        user.last_login = datetime.utcnow()
        user.failed_login_attempts = 0
        user.locked_until = None
        await db.commit()
    
    async def increment_failed_login(self, db: AsyncSession, user: AdminUser):
        """Увеличить счетчик неудачных попыток"""
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 5:
            user.locked_until = datetime.utcnow() + timedelta(minutes=15)
        await db.commit()
    
    def is_locked(self, user: AdminUser) -> bool:
        """Проверка блокировки аккаунта"""
        if user.locked_until and user.locked_until > datetime.utcnow():
            return True
        return False

# Создаем экземпляр для использования в других модулях
admin_user = CRUDAdminUser()