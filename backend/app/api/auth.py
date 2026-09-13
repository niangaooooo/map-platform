"""认证路由：登录、注册、刷新、登出、当前用户。"""
import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession, ip_of, rate_limit
from app.core.config import get_settings
from app.core.security import (
    create_access_token_for,
    hash_password,
    verify_password,
)
from app.models import RefreshToken, User
from app.schemas import LoginRequest, MessageOut, RefreshRequest, RegisterRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _fingerprint(request: Request) -> str:
    return hashlib.sha256(ip_of(request).encode()).hexdigest()[:24]


async def _issue_tokens(db: AsyncSession, user: User, request: Request) -> TokenResponse:
    settings = get_settings()
    refresh_token = secrets.token_urlsafe(48)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hashlib.sha256(refresh_token.encode()).hexdigest(),
            expires_at=datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    await db.commit()
    return TokenResponse(
        access_token=create_access_token_for(user.id),
        refresh_token=refresh_token,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: DbSession) -> TokenResponse:
    await rate_limit(request, f"login:{_fingerprint(request)}:{body.username}", get_settings().LOGIN_RATE_LIMIT_PER_MINUTE)
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被禁用")
    return await _issue_tokens(db, user, request)


@router.post("/register", response_model=TokenResponse)
async def register(body: RegisterRequest, request: Request, db: DbSession) -> TokenResponse:
    if not get_settings().ALLOW_REGISTER:
        raise HTTPException(status_code=403, detail="未开放注册，请联系管理员创建账号")
    exists = await db.execute(select(User).where((User.username == body.username) | (User.email == body.email)))
    if exists.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="用户名或邮箱已被使用")
    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name or body.username,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return await _issue_tokens(db, user, request)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, request: Request, db: DbSession) -> TokenResponse:
    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    token = result.scalar_one_or_none()
    if token is None or token.revoked_at is not None or token.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=401, detail="刷新凭证无效或已过期")
    user = await db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不可用")
    token.revoked_at = datetime.now(UTC)  # 单次使用
    await db.commit()
    return await _issue_tokens(db, user, request)


@router.post("/logout", response_model=MessageOut)
async def logout(body: RefreshRequest, db: DbSession) -> MessageOut:
    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    token = result.scalar_one_or_none()
    if token is not None:
        token.revoked_at = datetime.now(UTC)
        await db.commit()
    return MessageOut(msg="已退出")


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
