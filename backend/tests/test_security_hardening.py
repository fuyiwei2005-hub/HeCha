"""安全加固回归。

锁住的都是「一旦退化就是事故」的性质：
- 登出必须在服务端吊销令牌（而不是前端删一下 localStorage 就完事）；
- 签发的令牌必须带 jti，否则吊销无从谈起；
- 已吊销的令牌连图片接口（?token=）也要拒 —— 那是绕过 Authorization 头的后门；
- CORS 绝不允许通配符 + 凭证同时开启（Starlette 会反射任意 Origin）；
- Redis 挂掉时限流必须退回内存，而不是直接放行。
"""
import uuid

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core import token_blacklist
from app.core.config import get_settings
from app.core.rate_limit import RateLimiter
from app.main import app


PASSWORD = "A-secure-test-password-123"


def register_and_login(client: TestClient) -> tuple[str, str]:
    username = f"sec_{uuid.uuid4().hex[:16]}"
    assert client.post(
        "/api/auth/register", json={"username": username, "password": PASSWORD}
    ).status_code == 201
    resp = client.post("/api/auth/login", data={"username": username, "password": PASSWORD})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return username, token


def test_token_carries_jti():
    with TestClient(app) as client:
        _, token = register_and_login(client)
    payload = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    assert payload.get("jti"), "令牌缺少 jti，登出吊销将无法工作"


def test_logout_revokes_token():
    with TestClient(app) as client:
        _, token = register_and_login(client)
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/auth/me", headers=headers).status_code == 200
        assert client.post("/api/auth/logout", headers=headers).status_code == 204
        # 同一张令牌立刻失效 —— 这是「真登出」和「删 localStorage」的分界线
        assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_logout_is_idempotent_for_garbage_token():
    """登出接口必须永远「成功」：调用方的意图是结束会话，报 401 反而卡住前端。"""
    with TestClient(app) as client:
        assert client.post(
            "/api/auth/logout", headers={"Authorization": "Bearer not-a-jwt"}
        ).status_code == 204


def test_revoked_token_cannot_fetch_result_image():
    """走 Authorization 头的结果接口也必须查吊销名单。

    （历史上这个接口还接受 ?token=<JWT> 以便 <img> 直接引用，
    那会把 12 小时有效的会话凭据写进 URL 和 nginx 访问日志。
    现在改为短时签名票据，见下面两条用例。）
    """
    import io

    from PIL import Image

    def png_bytes() -> bytes:
        out = io.BytesIO()
        Image.new("RGB", (16, 16), "green").save(out, "PNG")
        return out.getvalue()

    with TestClient(app) as client:
        _, token = register_and_login(client)
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post(
            "/api/detections/image", headers=headers,
            files={"file": ("a.png", png_bytes(), "image/png")},
        ).json()
        url = f"/api/detections/{created['id']}/result"

        assert client.get(url, headers=headers).status_code == 200

        assert client.post("/api/auth/logout", headers=headers).status_code == 204
        assert client.get(url, headers=headers).status_code == 401


def test_result_url_never_contains_the_jwt():
    """结果接口不再接受 ?token= —— 会话凭据不允许出现在 URL 里。"""
    import io

    from PIL import Image

    def png_bytes() -> bytes:
        out = io.BytesIO()
        Image.new("RGB", (16, 16), "green").save(out, "PNG")
        return out.getvalue()

    with TestClient(app) as client:
        _, token = register_and_login(client)
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post(
            "/api/detections/image", headers=headers,
            files={"file": ("a.png", png_bytes(), "image/png")},
        ).json()
        # 旧的凭据式查询参数必须被拒绝
        assert client.get(
            f"/api/detections/{created['id']}/result", params={"token": token}
        ).status_code == 401, "结果接口仍在接受 ?token=<JWT>，凭据会进访问日志"


def test_result_ticket_is_scoped_and_expires():
    """票据必须只对签发给它的那一条结果有效。"""
    import io

    from PIL import Image

    from app.api.detections import make_result_ticket, verify_result_ticket

    def png_bytes() -> bytes:
        out = io.BytesIO()
        Image.new("RGB", (16, 16), "green").save(out, "PNG")
        return out.getvalue()

    with TestClient(app) as client:
        _, token = register_and_login(client)
        headers = {"Authorization": f"Bearer {token}"}
        first = client.post(
            "/api/detections/image", headers=headers,
            files={"file": ("a.png", png_bytes(), "image/png")},
        ).json()
        second = client.post(
            "/api/detections/image", headers=headers,
            files={"file": ("b.png", png_bytes(), "image/png")},
        ).json()

        # 换取票据需要正常鉴权
        assert client.get(
            f"/api/detections/{first['id']}/result-ticket"
        ).status_code == 401
        ticket_resp = client.get(
            f"/api/detections/{first['id']}/result-ticket", headers=headers
        )
        assert ticket_resp.status_code == 200
        url = ticket_resp.json()["url"]
        assert "token=" not in url, "票据 URL 里不应再出现 token"
        assert "ticket=" in url

        # 票据可以直接取文件（这就是 <img src> 的用法）
        assert client.get(url).status_code == 200

        # 但同一张票据不能拿来取别人的结果
        stolen = url.replace(first["id"], second["id"])
        assert client.get(stolen).status_code == 401, "票据未绑定 detection_id"

        # 篡改签名 / 过期的票据一律拒绝
        assert verify_result_ticket(first["id"], "9999999999-deadbeef") is False
        assert verify_result_ticket(first["id"], "1-whatever") is False
        assert verify_result_ticket(first["id"], None) is False
        assert verify_result_ticket(first["id"], make_result_ticket(first["id"])) is True


def test_cors_does_not_reflect_arbitrary_origin():
    """allow_origins 为白名单时，任意 Origin 的预检不能被放行。"""
    with TestClient(app) as client:
        resp = client.options(
            "/api/auth/me",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        acao = resp.headers.get("access-control-allow-origin", "")
        assert acao != "https://evil.example", "CORS 把任意来源反射回去了"


@pytest.mark.asyncio
async def test_rate_limiter_falls_back_to_memory(monkeypatch):
    """Redis 不可用时限流必须退回内存计数，而不是放行。"""

    async def no_redis():
        return None

    monkeypatch.setattr("app.core.redis_guard.get_client", no_redis)

    limiter = RateLimiter(max_requests=3, window_seconds=60, name="test")
    for _ in range(3):
        await limiter.check_async("1.2.3.4")
    with pytest.raises(HTTPException) as exc_info:
        await limiter.check_async("1.2.3.4")
    assert exc_info.value.status_code == 429
    assert exc_info.value.headers.get("Retry-After")
    # 换个 key 不受影响
    await limiter.check_async("5.6.7.8")


def test_memory_limiter_expiry_logic():
    """内存兜底的窗口过期后必须放行，不能永久封禁。"""
    limiter = RateLimiter(max_requests=2, window_seconds=60, name="test2")
    limiter.check("ip")
    limiter.check("ip")
    # 手动把窗口内的记录挪出窗外
    import collections
    import time

    bucket = limiter._hits["ip"]
    limiter._hits["ip"] = collections.deque(t - 120 for t in bucket)
    limiter.check("ip")  # 不应抛 429
    assert time.monotonic() - list(limiter._hits["ip"])[0] < 60
