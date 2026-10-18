"""JWT 吊销名单。

JWT 是无状态的，服务端签发完就不再过问。这带来一个实际漏洞：
用户点「退出登录」只是前端把 token 删了，token 本身在过期前始终有效 ——
谁把它抄走（浏览器历史、抓包、共用电脑）都能继续冒充该用户。

这里补上服务端侧吊销：登出时把 token 的 jti 记进 Redis，
校验时查一次。Redis 不可用时退回进程内字典，保证登出永远有效
（单机部署下内存字典本来就是全部）。
"""
from __future__ import annotations

import logging
import threading
import time

from app.core.redis_guard import get_client, invalidate

logger = logging.getLogger(__name__)

_PREFIX = "pestguard:jti:"

# Redis 挂掉时的兜底。key -> 失效时刻（time.monotonic）
_memory: dict[str, float] = {}
_lock = threading.Lock()


def _purge_expired(now: float) -> None:
    """顺手清掉过期的条目，避免字典只增不减。"""
    if len(_memory) < 512:
        return
    for key in [k for k, deadline in _memory.items() if deadline <= now]:
        _memory.pop(key, None)


def _remember(jti: str, ttl: int) -> None:
    with _lock:
        _memory[jti] = time.monotonic() + ttl
        _purge_expired(time.monotonic())


def _remembered(jti: str) -> bool:
    now = time.monotonic()
    with _lock:
        deadline = _memory.get(jti)
        if deadline is None:
            return False
        if deadline <= now:
            _memory.pop(jti, None)
            return False
        return True


async def revoke(jti: str, ttl_seconds: int) -> None:
    """吊销某个 jti，ttl 取该 token 的剩余有效期即可，过期后无需再占空间。"""
    if not jti or ttl_seconds <= 0:
        return
    _remember(jti, ttl_seconds)
    client = await get_client()
    if client is None:
        # Redis 不可用时内存兜底已经生效，登出仍然有效，只是多实例间不同步
        return
    try:
        await client.setex(f"{_PREFIX}{jti}", ttl_seconds, "1")
    except Exception as exc:  # noqa: BLE001
        invalidate()
        logger.debug("jti 吊销未能写入 Redis（已用内存兜底）: %s", exc.__class__.__name__)


async def is_revoked(jti: str | None) -> bool:
    """查询 jti 是否已被吊销。任一存储命中即视为吊销。"""
    if not jti:
        return False
    if _remembered(jti):
        return True
    client = await get_client()
    if client is None:
        return False
    try:
        return bool(await client.exists(f"{_PREFIX}{jti}"))
    except Exception:  # noqa: BLE001
        invalidate()
        return False
