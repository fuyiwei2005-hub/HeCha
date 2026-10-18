"""健壮性回归：任务超时结算、单条查询、限流 IP 取值。

这些都是「不报错但用户体验很差」的问题，只能靠断言锁住：
- Worker 没启动时视频永远停在 queued，前端一直转圈；
- 图片记录只能拉全量列表，没有按 id 查询的接口；
- 限流信任可伪造的 X-Forwarded-For，等于没限流。
"""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.core.rate_limit import get_client_ip
from app.main import app
from app.models.detection import Detection
from app.services.task_maintenance import reconcile_tasks

PASSWORD = "A-secure-test-password-123"


def _login(client: TestClient) -> tuple[dict[str, str], int]:
    username = f"u_{uuid4().hex[:12]}"
    assert client.post(
        "/api/auth/register", json={"username": username, "password": PASSWORD}
    ).status_code == 201
    token = client.post(
        "/api/auth/login", data={"username": username, "password": PASSWORD}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return headers, client.get("/api/auth/me", headers=headers).json()["id"]


def _insert_video(
    user_id: int, minutes_ago: int, *, status: str = "queued",
    started_minutes_ago: int | None = None,
) -> str:
    """直插一条视频任务，created_at 回拨指定分钟数。

    started_minutes_ago 用于模拟 worker 已经开始处理的记录
    （processing + video_meta.started_at）。
    """

    async def _run() -> str:
        async with SessionLocal() as db:
            meta = None
            if started_minutes_ago is not None:
                meta = {
                    "started_at": (
                        datetime.now(timezone.utc).replace(tzinfo=None)
                        - timedelta(minutes=started_minutes_ago)
                    ).isoformat()
                }
            item = Detection(
                id=str(uuid4()), user_id=user_id, media_type="video",
                original_name="v.mp4", stored_name=f"{uuid4().hex}.mp4",
                status=status, predictions=[], video_meta=meta,
                heartbeat_at=(datetime.now(timezone.utc) - timedelta(minutes=started_minutes_ago)) if started_minutes_ago is not None else None,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None)
                - timedelta(minutes=minutes_ago),
            )
            db.add(item)
            await db.commit()
            return item.id

    return asyncio.run(_run())


def test_slow_but_healthy_video_is_not_marked_failed():
    """正在处理、且处理时间没超限的任务不能被判失败。

    回归用例：过期结算原先一律以 created_at（= 上传时刻）起算，
    于是一个排队等了 4 分钟、刚开始跑的正常视频，会在上传满 5 分钟时
    被翻成 failed 并提示"请确认 Worker 是否已启动"，
    等 worker 跑完又悄悄变回 completed —— 前端出现自相矛盾的状态。
    worker 的 job_timeout 是 10 分钟，所以这种情况完全正常。
    """
    with TestClient(app) as client:
        headers, user_id = _login(client)
        # 上传 9 分钟前，但 1 分钟前才开始处理 —— 属于健康的长任务
        slow_id = _insert_video(
            user_id, minutes_ago=9, status="processing", started_minutes_ago=1
        )
        rows = client.get("/api/detections", headers=headers).json()
        by_id = {r["id"]: r for r in rows}
        assert by_id[slow_id]["status"] == "processing", (
            "正常处理中的任务被误判为失败（超时基准应该用 started_at，不是 created_at）"
        )


def test_video_stuck_in_processing_is_eventually_failed():
    """真的卡住（开始处理超过阈值）的任务仍要结算成 failed。"""
    with TestClient(app) as client:
        headers, user_id = _login(client)
        stuck_id = _insert_video(
            user_id, minutes_ago=30, status="processing", started_minutes_ago=30
        )
        asyncio.run(reconcile_tasks())
        rows = client.get("/api/detections", headers=headers).json()
        by_id = {r["id"]: r for r in rows}
        assert by_id[stuck_id]["status"] == "failed"
        assert "超时" in (by_id[stuck_id]["error"] or "")


def test_stale_video_job_is_marked_failed():
    """卡住的视频任务在列表接口里被结算成 failed，而不是永远 queued。"""
    with TestClient(app) as client:
        headers, user_id = _login(client)
        old_id = _insert_video(user_id, minutes_ago=30)
        fresh_id = _insert_video(user_id, minutes_ago=1)
        asyncio.run(reconcile_tasks())

        rows = client.get("/api/detections", headers=headers).json()
        by_id = {r["id"]: r for r in rows}

        assert by_id[old_id]["status"] == "failed"
        assert "超时" in (by_id[old_id]["error"] or "")
        # 刚提交的任务不能被误伤
        assert by_id[fresh_id]["status"] == "queued"


def test_get_detection_by_id_and_isolation():
    """GET /detections/{id} 补齐，且严格按用户隔离。"""
    with TestClient(app) as client:
        first, user_a = _login(client)
        second, _ = _login(client)

        did = _insert_video(user_a, minutes_ago=0)
        response = client.get(f"/api/detections/{did}", headers=first)
        assert response.status_code == 200
        assert response.json()["id"] == did

        assert client.get(f"/api/detections/{did}", headers=second).status_code == 404
        assert client.get("/api/detections/does-not-exist", headers=first).status_code == 404


def test_client_ip_ignores_spoofable_header_by_default(monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "trust_proxy", False)
    scope = {
        "type": "http",
        "headers": [(b"x-forwarded-for", b"9.9.9.9")],
        "client": ("1.2.3.4", 5555),
    }
    assert get_client_ip(Request(scope)) == "1.2.3.4"

    monkeypatch.setattr(settings, "trust_proxy", True)
    assert get_client_ip(Request(scope)) == "9.9.9.9"


def test_rate_limiter_blocks_burst():
    """同一 IP 连续请求超过阈值应抛 429。"""
    from app.core.rate_limit import RateLimiter
    from fastapi import HTTPException

    limiter = RateLimiter(max_requests=3, window_seconds=60)
    for _ in range(3):
        limiter.check("1.1.1.1")
    with pytest.raises(HTTPException) as exc:
        limiter.check("1.1.1.1")
    assert exc.value.status_code == 429
    # 不同 IP 互不影响
    limiter.check("2.2.2.2")
