from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.token_blacklist import is_revoked
from app.models.user import User


settings = get_settings()
password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def create_access_token(user_id: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    # jti 是这张令牌的唯一编号，登出时靠它在服务端吊销
    # ——没有它，无状态 JWT 就没法被主动作废。
    return jwt.encode(
        {"sub": str(user_id), "exp": expires, "jti": uuid4().hex},
        settings.secret_key,
        algorithm="HS256",
    )


def remaining_seconds(token: str) -> int:
    """返回 token 剩余有效秒数，用于设定吊销名单的 TTL（已过期返回 0）。"""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        exp = int(payload.get("exp") or 0)
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        return 0
    left = exp - int(datetime.now(timezone.utc).timestamp())
    return max(0, left)


def _decode_payload(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        raise unauthorized_error()


def unauthorized_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def decode_user_id(token: str) -> int:
    """解码 JWT 并返回 user_id；失败抛 401。供 <img> 走 ?token= 的接口复用。

    注意：这里不做吊销校验（同步上下文，无法查 Redis）。
    需要校验登出状态的入口请用下面的 ensure_not_revoked。
    """
    try:
        return int(_decode_payload(token)["sub"])
    except (KeyError, TypeError, ValueError):
        raise unauthorized_error()


async def ensure_not_revoked(token: str) -> None:
    """已登出的 token 必须拒绝 —— 否则「退出登录」只是自欺欺人。"""
    payload = _decode_payload(token)
    jti = payload.get("jti")
    if not jti:
        return  # 老版本签发的 token 没有 jti，无从吊销，放行
    if await is_revoked(str(jti)):
        raise unauthorized_error()


async def current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # 先查吊销，再解 subject：已经登出的 token 不该再走到数据库查询
        await ensure_not_revoked(token)
        user_id = decode_user_id(token)
    except HTTPException:
        raise unauthorized
    user = await db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if not user:
        raise unauthorized
    return user

