# app/api/v1/auth.py
from typing import Optional
from fastapi import APIRouter, Depends, Request, Response, HTTPException, status, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession


from app.core.config import Settings
from app.deps import get_db
from app.services.auth import AuthService
from app.schemas.auth import (
    LoginResponse, LogoutResponse, AuthStatus, 
    UserResponse, CurrentUser
)
from app.models.user import User, UserSession

# Инициализация
settings = Settings()
auth_service = AuthService(settings)
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/status")
async def get_auth_status(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> AuthStatus:
    """Получить статус авторизации"""
    
    # Получаем токен из cookies
    session_token = request.cookies.get("session_token")
    
    if not session_token:
        return AuthStatus(is_authenticated=False, user=None)
    
    # Проверяем сессию
    from app.crud.user import session_crud, user_crud
    session = await session_crud.get_by_token(db, session_token)
    
    if not session or not session.is_valid:
        return AuthStatus(is_authenticated=False, user=None)
    
    # Получаем пользователя
    user = await user_crud.get_by_id(db, session.user_id)
    if not user or not user.is_active:
        return AuthStatus(is_authenticated=False, user=None)
    
    return AuthStatus(
        is_authenticated=True,
        user=UserResponse.from_orm(user)
    )


@router.get("/me")
async def get_current_user_info(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> CurrentUser:
    """Получить информацию о текущем пользователе"""
    
    # Получаем токен из cookies
    session_token = request.cookies.get("session_token")
    
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    # Проверяем сессию
    from app.crud.user import session_crud, user_crud
    session = await session_crud.get_by_token(db, session_token)
    
    if not session or not session.is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session"
        )
    
    # Получаем пользователя
    user = await user_crud.get_by_id(db, session.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    return CurrentUser.from_orm(user)


@router.get("/yandex/login")
async def yandex_login(
    request: Request,
    redirect_url: Optional[str] = Query(None, description="URL для редиректа после авторизации")
):
    """Начать авторизацию через Yandex"""
    
    # Генерируем state для защиты от CSRF
    state = auth_service.generate_state_token()
    
    # Сохраняем state и redirect_url в сессии
    # В продакшене лучше использовать Redis или базу данных
    if not hasattr(request, 'session'):
        request.session = {}
    
    request.session["oauth_state"] = state
    if redirect_url:
        request.session["redirect_after_auth"] = redirect_url
    
    # Получаем URL для авторизации
    auth_url = auth_service.get_authorization_url(state)
    
    return RedirectResponse(url=auth_url)


@router.get("/yandex/callback")
async def yandex_callback(
    request: Request,
    response: Response,
    code: str = Query(..., description="Код авторизации от Yandex"),
    state: str = Query(..., description="State параметр"),
    error: Optional[str] = Query(None, description="Ошибка от OAuth провайдера"),
    db: AsyncSession = Depends(get_db)
):
    """Обработать callback от Yandex OAuth"""
    
    # Проверяем наличие ошибки
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth error: {error}"
        )
    
    # Проверяем state для защиты от CSRF
    if not hasattr(request, 'session'):
        request.session = {}
        
    expected_state = request.session.get("oauth_state")
    if not expected_state or expected_state != state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state parameter"
        )
    
    try:
        # Обрабатываем OAuth callback
        user, session = await auth_service.process_oauth_callback(
            code=code,
            state=state,
            request=request,
            db=db
        )
        
        # Устанавливаем cookies
        auth_service.set_session_cookies(
            response=response,
            session=session,
            secure=False  # В продакшене установите True для HTTPS
        )
        
        # Очищаем временные данные из сессии
        request.session.pop("oauth_state", None)
        redirect_url = request.session.pop("redirect_after_auth", None)
        
        # Если есть URL для редиректа, перенаправляем туда
        if redirect_url:
            return RedirectResponse(url=redirect_url)
        
        # Иначе перенаправляем на главную страницу админки
        return RedirectResponse(url="/admin")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication failed: {str(e)}"
        )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> LogoutResponse:
    """Выйти из системы"""
    
    # Получаем токен из cookies
    session_token = request.cookies.get("session_token")
    
    if session_token:
        from app.crud.user import session_crud
        session = await session_crud.get_by_token(db, session_token)
        if session:
            await auth_service.logout(session, db)
    
    # Очищаем cookies
    auth_service.clear_session_cookies(response)
    
    return LogoutResponse(message="Successfully logged out")


@router.post("/logout-all")
async def logout_all(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> LogoutResponse:
    """Выйти из всех устройств"""
    
    # Получаем текущего пользователя
    session_token = request.cookies.get("session_token")
    
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    from app.crud.user import session_crud, user_crud
    session = await session_crud.get_by_token(db, session_token)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session"
        )
    
    user = await user_crud.get_by_id(db, session.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    # Выходим из всех сессий
    await auth_service.logout_all(user.id, db)
    
    # Очищаем cookies
    auth_service.clear_session_cookies(response)
    
    return LogoutResponse(message="Successfully logged out from all devices")


# Тестовые роуты (можно убрать в продакшене)
@router.get("/test/protected")
async def test_protected_route(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Тестовый защищенный роут"""
    
    # Простая проверка авторизации
    session_token = request.cookies.get("session_token")
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    from app.crud.user import session_crud, user_crud
    session = await session_crud.get_by_token(db, session_token)
    if not session or not session.is_valid:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    user = await user_crud.get_by_id(db, session.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return {
        "message": "This is a protected route",
        "user": {
            "id": user.id,
            "email": user.email,
            "yandex_id": user.yandex_id
        },
        "timestamp": "2025-06-02T12:00:00Z"
    }


@router.get("/test/admin")
async def test_admin_route(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Тестовый админский роут"""
    
    # Проверка авторизации и прав администратора
    session_token = request.cookies.get("session_token")
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    from app.crud.user import session_crud, user_crud
    session = await session_crud.get_by_token(db, session_token)
    if not session or not session.is_valid:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    user = await user_crud.get_by_id(db, session.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    if not user.is_admin and not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    return {
        "message": "This is an admin route",
        "user": {
            "id": user.id,
            "email": user.email,
            "is_admin": user.is_admin,
            "is_superuser": user.is_superuser,
            "yandex_id": user.yandex_id
        },
        "timestamp": "2025-06-02T12:00:00Z"
    }