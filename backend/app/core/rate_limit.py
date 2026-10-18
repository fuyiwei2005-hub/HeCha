"""限流：Redis 集中计数，Redis 不可用时退回进程内存。

为什么不能只放内存：限流的目的是挡住暴力枚举。多 worker 或多实例部署时，
每个进程各有一份计数，攻击者只要把请求打散就能拿到 N 倍配额；
单机单进程下内存是够的，但那只是"暂时没出问题"，不是"设计正确"。

Redis 挂掉时必须降级而不是放行：宁可退回到内存计数（单机语义），
也不能因为连不上 Redis 就让接口裸奔。
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Deque, Dict

from fastapi import HTTPException, Request

from app.core.config import get_settings
from app.core.redis_guard import get_client, invalidate

logger = logging.getLogger(__name__)

_REDIS_PREFIX = "pestguard:rl:"


class RateLimiter:
    def __init__(
        self, max_requests: int = 10, window_seconds: int = 60, name: str = "default"
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.name = name
        # 内存兜底桶。Redis 不可用时接管，语义与 Redis 侧一致（固定窗口）
        self._hits: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    # ---------- 对外接口 ----------

    async def check_async(self, key: str) -> None:
        """优先走 Redis；Redis 不可用则退回内存。"""
        try:
            await self._check_redis(key)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.debug("Redis 限流不可用，退回内存计数：%s", exc.__class__.__name__)
            self.check(key)

    def check(self, key: str) -> None:
        """纯内存计数（同步）。供无事件循环的上下文与 Redis 降级时使用。"""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._hits.setdefault(key, deque())
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                retry_after = int(self.window_seconds - (now - bucket[0])) + 1
                raise HTTPException(
                    status_code=429,
                    detail=f"操作过于频繁，请 {retry_after} 秒后再试",
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.append(now)
            # 顺手回收长期不活跃的 key：否则字典会随访问过的 IP 数量无限增长
            if len(self._hits) > 1024:
                for dead in [k for k, v in self._hits.items() if not v]:
                    self._hits.pop(dead, None)

    def reset(self) -> None:
        """清空内存计数（测试用）。"""
        with self._lock:
            self._hits.clear()

    # ---------- 内部实现 ----------

    async def _check_redis(self, key: str) -> None:
        client = await get_client()
        if client is None:
            # 拿不到连接就交给调用方的内存兜底：抛一个非 HTTPException，
            # check_async 会捕获并降级，绝不能因为 Redis 挂了就放行
            raise RuntimeError("redis unavailable")
        redis_key = f"{_REDIS_PREFIX}{self.name}:{key}"
        try:
            async with client.pipeline(transaction=True) as pipe:
                pipe.incr(redis_key)
                pipe.ttl(redis_key)
                count, ttl = await pipe.execute()
            # 首次计数（或 TTL 因故丢失）时补上过期时间，
            # 否则这个 key 会永久留在 Redis 里，等于把用户永久封禁
            if not ttl or ttl < 0:
                await client.expire(redis_key, self.window_seconds)
                ttl = self.window_seconds
            if count > self.max_requests:
                raise HTTPException(
                    status_code=429,
                    detail=f"操作过于频繁，请 {max(int(ttl), 1)} 秒后再试",
                    headers={"Retry-After": str(max(int(ttl), 1))},
                )
        except Exception:  # noqa: BLE001
            invalidate()
            raise


# 全局实例：登录/注册共用，同一 IP 每分钟 10 次
auth_limiter = RateLimiter(max_requests=10, window_seconds=60, name="auth")

# 大模型接口的按用户限流。
# 图片检测与多轮追问都会真实调用 DeepSeek（花的是真金白银），
# 而这两个接口此前**没有任何上限** —— 一个脚本刷一晚就能把额度烧光。
# 20 次/分钟对正常使用（一次演示几十张图）绰绰有余，又能挡住滥用。
llm_limiter = RateLimiter(max_requests=20, window_seconds=60, name="llm")


async def check_llm_quota(user_id: int) -> None:
    """按用户（而不是按 IP）限制大模型调用频率。

    用 user_id 而不是 IP：同一间实验室/同一出口 IP 下有多个用户是常态，
    按 IP 限流会误伤同事；而滥用者换个 IP 就能绕过按 IP 的限制。
    """
    await llm_limiter.check_async(f"u{user_id}")


def get_client_ip(request: Request) -> str:
    """从 Request 提取客户端 IP。

    X-Forwarded-For 是客户端可伪造的：直接信任它等于把限流的钥匙交给攻击者，
    换一个头就能无限次撞密码。所以只有在明确配置了可信代理（TRUST_PROXY=true）时才采用。

    取最左一段（原始客户端）：Nginx 会在右边逐跳追加，真正的客户端在最前面。
    """
    if get_settings().trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
    return request.client.host if request.client else "unknown"
