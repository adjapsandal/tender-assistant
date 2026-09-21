from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, HTTPException, Request, Response, status
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from common.config import config
from database.repositories import Repositories
from web.dependencies import get_session
from web.utils.hashing import Hasher


async def create_access_token(data: dict[str, Any]) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = data.copy()
    payload.update({"exp": expire})
    return jwt.encode(payload, config.SECRET_KEY, config.ALGORITHM)


async def verify_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, config.SECRET_KEY, config.ALGORITHM)
        return payload
    except JWTError:
        return None


async def set_access_token_cookie(response: Response, access_token: str, expires_days: int = 30) -> None:
    response.set_cookie(
        key="access_token",
        value=access_token,
        # Кука с токеном не должна читаться из JavaScript: иначе любой XSS
        # на странице уводит сессию. Фронтенд её и не читает — запросы идут
        # с credentials, браузер подставляет куку сам.
        httponly=True,
        max_age=expires_days * 24 * 60 * 60,
        path="/",
        secure=True,
        samesite="none",
    )


async def delete_access_token_cookie(response: Response) -> None:
    # Атрибуты должны совпадать с теми, с которыми кука ставилась,
    # иначе браузер её не удалит.
    response.delete_cookie(
        key="access_token",
        path="/",
        httponly=True,
        secure=True,
        samesite="none",
    )


async def get_token_from_cookie(request: Request) -> str | None:
    return request.cookies.get("access_token")


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    token = await get_token_from_cookie(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    payload = await verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    repos = Repositories(session)
    user = await repos.web_user.get(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


async def auth_user(email: str, password: str, session: AsyncSession):
    repos = Repositories(session)
    user = await repos.web_user.get_by_email(email)
    if not user:
        return None
    if not await Hasher.verify_password(password, user.hashed_password):
        return None
    return user
