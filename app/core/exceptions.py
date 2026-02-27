from typing import Any, NoReturn

from fastapi import HTTPException
from starlette import status


def raise_400(message: str = "Bad request") -> NoReturn:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def raise_401(message: str = "Not authenticated") -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": "Bearer"},
    )


def raise_403(message: str = "Forbidden") -> NoReturn:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)


def raise_404(message: str = "Not found", *, entity: str = None, id: Any = None) -> NoReturn:
    if entity and id:
        message = f"{entity} {id} not found"
    elif entity:
        message = f"{entity} not found"
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def raise_409(message: str = "Conflict") -> NoReturn:
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def raise_429(message: str = "Too many requests") -> NoReturn:
    raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=message)


def raise_500(message: str = "Internal server error") -> NoReturn:
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message)
