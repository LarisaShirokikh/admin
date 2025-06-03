from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str
    redis_url: str


    SECRET_KEY: str = Field(..., env="SECRET_KEY") 
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")




    # === OAuth Yandex настройки ===
    YANDEX_CLIENT_ID: str = Field(..., env="YANDEX_CLIENT_ID")
    YANDEX_CLIENT_SECRET: str = Field(..., env="YANDEX_CLIENT_SECRET")
    YANDEX_REDIRECT_URI: str = Field(default="http://localhost:8000/api/v1/auth/yandex/callback", env="YANDEX_REDIRECT_URI")

    # URLs для OAuth
    YANDEX_AUTH_URL: str = "https://oauth.yandex.ru/authorize"
    YANDEX_TOKEN_URL: str = "https://oauth.yandex.ru/token"
    YANDEX_USER_INFO_URL: str = "https://login.yandex.ru/info"
    YANDEX_SCOPE: str = "login:email login:info"

    # Время жизни токенов
    SESSION_EXPIRE_HOURS: int = Field(default=24, env="SESSION_EXPIRE_HOURS")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, env="REFRESH_TOKEN_EXPIRE_DAYS")

    # Администраторы по умолчанию (Yandex ID)
    DEFAULT_ADMIN_YANDEX_IDS: List[str] = Field(default=[], env="DEFAULT_ADMIN_YANDEX_IDS")

    @field_validator('DEFAULT_ADMIN_YANDEX_IDS', mode='before')
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            return [id_.strip() for id_ in v.split(',') if id_.strip()]
        elif isinstance(v, (int, float)):
            return [str(v)]  # Преобразуем число в строку и возвращаем как список
        elif isinstance(v, list):
            return [str(item) for item in v]  # Преобразуем все элементы в строки
        return v or []

settings = Settings()