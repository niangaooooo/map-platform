"""公共依赖：当前用户、项目成员校验、限流。"""
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.redis import get_redis
from app.db.session import get_db
from app.models import User


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """从 Authorization: Bearer 或 X-Auth-Token 头读取 JWT 并返回用户。"""
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else request.headers.get("X-Auth-Token", "")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="凭证无效或已过期") from None
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="凭证类型错误")
    user = await db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]


def ip_of(request: Request) -> str:
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


async def rate_limit(request: Request, bucket: str, limit_per_minute: int) -> None:
    """基于 Redis 的滑动窗口限流（用于登录等敏感接口）。"""
    redis = get_redis()
    key = f"rl:{bucket}"
    try:
        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 60)
        count, _ = await pipe.execute()
        if int(count) > limit_per_minute:
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
    except HTTPException:
        raise
    except Exception:
        # 限流是辅助能力：Redis 异常（连接池满/抖动）时放行，避免登录被误伤
        pass
