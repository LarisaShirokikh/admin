from datetime import datetime, timedelta
from typing import List, Optional

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminUser
from app.schemas.admin import AdminUserCreate

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

LOCK_AFTER_ATTEMPTS = 5
LOCK_DURATION_MINUTES = 15


async def get(db: AsyncSession, user_id: int) -> Optional[AdminUser]:
    result = await db.execute(select(AdminUser).where(AdminUser.id == user_id))
    return result.scalar_one_or_none()


async def get_by_username(db: AsyncSession, username: str) -> Optional[AdminUser]:
    result = await db.execute(select(AdminUser).where(AdminUser.username == username))
    return result.scalar_one_or_none()


async def get_by_email(db: AsyncSession, email: str) -> Optional[AdminUser]:
    result = await db.execute(select(AdminUser).where(AdminUser.email == email))
    return result.scalar_one_or_none()


async def get_multi(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[AdminUser]:
    result = await db.execute(select(AdminUser).offset(skip).limit(limit))
    return result.scalars().all()


async def create(db: AsyncSession, data: AdminUserCreate) -> AdminUser:
    user = AdminUser(
        username=data.username,
        email=data.email,
        hashed_password=pwd_context.hash(data.password),
        is_active=data.is_active,
        is_superuser=data.is_superuser,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate(db: AsyncSession, username: str, password: str) -> Optional[AdminUser]:
    user = await get_by_username(db, username)
    if not user:
        return None
    if not pwd_context.verify(password, user.hashed_password):
        return None
    return user


def is_active(user: AdminUser) -> bool:
    return user.is_active


def is_superuser(user: AdminUser) -> bool:
    return user.is_superuser


def is_locked(user: AdminUser) -> bool:
    return bool(user.locked_until and user.locked_until > datetime.utcnow())


async def update_last_login(db: AsyncSession, user: AdminUser):
    user.last_login = datetime.utcnow()
    user.failed_login_attempts = 0
    user.locked_until = None
    await db.commit()


async def increment_failed_login(db: AsyncSession, user: AdminUser):
    user.failed_login_attempts += 1
    if user.failed_login_attempts >= LOCK_AFTER_ATTEMPTS:
        user.locked_until = datetime.utcnow() + timedelta(minutes=LOCK_DURATION_MINUTES)
    await db.commit()