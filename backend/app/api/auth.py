import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import auth_limiter, get_client_ip
from app.core.security import (
    create_access_token,
    current_user,
    hash_password,
    oauth2_scheme,
    remaining_seconds,
    verify_password,
)
from app.core.token_blacklist import revoke
from app.models.user import User
from app.schemas.auth import RegisterRequest, TokenResponse, UserResponse


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(payload: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    await auth_limiter.check_async(get_client_ip(request))
    username = payload.username.strip()
    user = User(
        username=username,
        email=(payload.email or None),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "该账号已被注册，请换一个")
    return user


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    # 登录名去空格：注册时 pydantic 会自动 trim，这里必须一致，
    # 否则用户输入 " abc " 注册成功、再用 " abc " 登录会 401（旧版就存在这个不一致）
    raw = (form.username or "").strip()
    if not raw:
        await auth_limiter.check_async(get_client_ip(request))
        raise HTTPException(401, "请输入账号")
    # 用户名与邮箱是两个独立命名空间，必须分开查，不能 or_() 一把梭：
    # 若 A 用户的 email 恰好等于 B 用户的 username，or_ 查到哪一行取决于
    # 数据库扫描顺序 —— 等于把 A 的密码校验用在 B 的账号上，是实打实的越权。
    # 先按 username 查，查不到再按 email 查（兼容 demo@example.com 这类老账号）。
    user = await db.scalar(select(User).where(User.username == raw))
    if user is None:
        user = await db.scalar(select(User).where(User.email == raw.lower()))
    if not user or not verify_password(form.password, user.password_hash):
        await auth_limiter.check_async(get_client_ip(request))
        raise HTTPException(401, "账号或密码不正确")
    return TokenResponse(
        access_token=create_access_token(user.id),
        user=UserResponse(id=user.id, username=user.username, email=user.email),
    )


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(current_user)):
    return user


@router.post("/logout", status_code=204)
async def logout(token: str = Depends(oauth2_scheme)):
    """退出登录：在服务端吊销这张令牌。

    只在前端 localStorage 里删掉 token 是不够的 —— token 本身在过期前
    一直有效，抄走就能继续用。这里把它的 jti 记进吊销名单，
    后续请求（含走 ?token= 的图片接口）一律拒绝。
    """
    # 即便 token 已过期或格式异常，登出也应当「成功」：
    # 调用方的意图是结束会话，报 401 反而会让前端卡在错误态。
    ttl = remaining_seconds(token)
    if ttl <= 0:
        return
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return
    await revoke(str(payload.get("jti") or ""), ttl)
