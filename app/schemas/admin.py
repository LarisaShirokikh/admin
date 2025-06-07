# app/schemas/admin.py
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import datetime

class AdminUserBase(BaseModel):
    username: str
    email: EmailStr
    is_active: bool = True
    is_superuser: bool = False

class AdminUserCreate(AdminUserBase):
    password: str
    confirm_password: str
    
    @field_validator('confirm_password')
    @classmethod
    def passwords_match(cls, v, info):
        if info.data and 'password' in info.data and v != info.data['password']:
            raise ValueError('passwords do not match')
        return v
    
    @field_validator('username')
    @classmethod
    def username_alphanumeric(cls, v):
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('username must be alphanumeric (with _ and - allowed)')
        if len(v) < 3 or len(v) > 20:
            raise ValueError('username must be between 3 and 20 characters')
        return v

class AdminUser(AdminUserBase):
    id: int
    created_at: datetime
    last_login: Optional[datetime]
    failed_login_attempts: int
    locked_until: Optional[datetime]
    
    class Config:
        from_attributes = True

class AdminLoginRequest(BaseModel):
    username: str
    password: str

class AdminLoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AdminUser