import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import WebUser
from database.repositories import Repositories
from web.dependencies import get_session
from web.schemas import (
    TokenResponse,
    UserLoginRequest,
    UserProfileResponse,
    UserRegisterRequest,
)
from web.utils.auth import (
    auth_user,
    create_access_token,
    delete_access_token_cookie,
    get_current_user,
    set_access_token_cookie,
)
from web.utils.hashing import Hasher

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/register", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserRegisterRequest,
    session: AsyncSession = Depends(get_session),
):
    repos = Repositories(session)

    existing = await repos.web_user.get_by_email(data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists",
        )

    company = await repos.company.create(name=data.company_name)

    hashed_password = await Hasher.get_password_hash(data.password)
    user = await repos.web_user.create_user(
        email=data.email,
        hashed_password=hashed_password,
        company_id=company.id,
    )

    await session.commit()
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    response: Response,
    data: UserLoginRequest,
    session: AsyncSession = Depends(get_session),
):
    user = await auth_user(data.email, data.password, session)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    token = await create_access_token({"user_id": user.id})
    await set_access_token_cookie(response, token)

    return TokenResponse(access_token=token)


@router.post("/logout")
async def logout(response: Response):
    await delete_access_token_cookie(response)
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserProfileResponse)
async def get_me(current_user: WebUser = Depends(get_current_user)):
    return current_user
