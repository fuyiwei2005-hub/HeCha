"""Redis 连接的统一入口：单连接池复用 + 故障冷却。

不要在各处 from_url() 现连现用：Redis 没起时，每次调用都要等一次连接失败，
而这两个调用点（限流、token 吊销）在**每个请求**上都会走一遍 ——
实测把整个测试套件从 24 秒拖到 130 秒，线上则等于给每个请求加一跳无谓延迟。

这里做两件事：
1. 池化复用：连上了就一直用这一个客户端（redis.asyncio 客户端本身是连接池，可并发）；
2. 故障冷却：连不上就记一笔，冷却期内直接返回 None，不再反复碰壁。
"""
from __future__ import annotations

import logging
import time
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# 连接失败后多久内不再重试。太短会退化成「每请求都碰一次壁」，
# 太长则在 Redis 恢复后迟迟不回切 —— 30 秒是两边都能接受的折中。
_COOLDOWN_SECONDS = 30.0

_client: Any = None
_down_until = 0.0


async def get_client() -> Any | None:
    """拿一个可用的 Redis 客户端；Redis 不可用返回 None（调用方需有兜底）。"""
    global _client, _down_until
    if _client is not None:
        return _client
    if time.monotonic() < _down_until:
        return None
    try:
        import redis.asyncio as aioredis

        settings = get_settings()
        candidate = aioredis.from_url(
            settings.redis_url,
            socket_connect_timeout=1,
            socket_timeout=2,
            decode_responses=True,
        )
        await candidate.ping()
        _client = candidate
        return _client
    except Exception as exc:  # noqa: BLE001
        logger.debug("Redis 连接失败（%s），%.0fs 内不再重试", exc.__class__.__name__, _COOLDOWN_SECONDS)
        _down_until = time.monotonic() + _COOLDOWN_SECONDS
        return None


def invalidate() -> None:
    """连接在使用过程中坏了 —— 丢弃它，让下次调用重新建立。"""
    global _client, _down_until
    if _client is not None:
        try:
            _client.close()
        except Exception:  # noqa: BLE001
            pass
    _client = None
    _down_until = time.monotonic() + _COOLDOWN_SECONDS


async def close() -> None:
    """进程退出时由 lifespan 调用。"""
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:  # noqa: BLE001
            pass
    _client = None
