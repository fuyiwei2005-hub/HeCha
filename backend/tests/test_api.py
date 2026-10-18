import io
from uuid import uuid4

from PIL import Image
from fastapi.testclient import TestClient

from app.main import app


def register_and_login(client: TestClient) -> tuple[dict[str, str], str]:
    username = f"user_{uuid4().hex[:16]}"
    password = "A-secure-test-password-123"
    response = client.post("/api/auth/register", json={"username": username, "password": password})
    assert response.status_code == 201
    response = client.post(
        "/api/auth/login", data={"username": username, "password": password}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}, username


def png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (32, 32), "green").save(output, "PNG")
    return output.getvalue()


def test_auth_image_detection_and_user_isolation():
    with TestClient(app) as client:
        first, _ = register_and_login(client)
        second, _ = register_and_login(client)

        response = client.post(
            "/api/detections/image",
            headers=first,
            files={"file": ("../../unsafe.png", png_bytes(), "image/png")},
        )
        assert response.status_code == 201
        detection = response.json()
        assert detection["media_type"] == "image"
        assert detection["status"] == "completed"

        assert len(client.get("/api/detections", headers=first).json()) == 1
        assert client.get("/api/detections", headers=second).json() == []
        assert client.get(detection["result_url"], headers=second).status_code == 404
        assert client.get(detection["result_url"], headers=first).status_code == 200


def test_rejects_unauthenticated_and_invalid_uploads():
    with TestClient(app) as client:
        headers, _ = register_and_login(client)
        assert client.get("/api/detections").status_code == 401
        response = client.post(
            "/api/detections/image",
            headers=headers,
            files={"file": ("fake.png", b"not an image", "image/png")},
        )
        assert response.status_code == 422


def test_statistics_are_scoped_to_current_user():
    with TestClient(app) as client:
        headers, _ = register_and_login(client)
        response = client.get("/api/statistics", headers=headers)
        assert response.status_code == 200
        assert response.json()["total_jobs"] == 0


def test_result_file_requires_auth_and_ownership():
    """结果文件：无 token 401；他人访问 404；本人 200"""
    with TestClient(app) as client:
        first, _ = register_and_login(client)
        second, _ = register_and_login(client)
        response = client.post(
            "/api/detections/image", headers=first,
            files={"file": ("leaf.png", png_bytes(), "image/png")},
        )
        url = response.json()["result_url"]
        assert client.get(url).status_code == 401
        assert client.get(url, headers=second).status_code == 404
        assert client.get(url, headers=first).status_code == 200


def test_original_image_persisted_and_removed_on_delete():
    """原图落盘，删除记录时一并清理"""
    from app.core.config import get_settings
    settings = get_settings()
    with TestClient(app) as client:
        headers, _ = register_and_login(client)
        created = client.post(
            "/api/detections/image", headers=headers,
            files={"file": ("leaf.png", png_bytes(), "image/png")},
        ).json()
        before = {p.name for p in settings.upload_dir.iterdir()}
        assert len(before) >= 1
        # 删除后应少一个文件（刚上传的原图）
        assert client.delete(f"/api/detections/{created['id']}", headers=headers).status_code == 204
        after = {p.name for p in settings.upload_dir.iterdir()}
        assert len(after) == len(before) - 1


def test_invalid_token_returns_401_on_result():
    """伪造 token 访问结果文件应 401"""
    with TestClient(app) as client:
        headers, _ = register_and_login(client)
        created = client.post(
            "/api/detections/image", headers=headers,
            files={"file": ("leaf.png", png_bytes(), "image/png")},
        ).json()
        bad = {"Authorization": "Bearer not.a.real.token"}
        assert client.get(created["result_url"], headers=bad).status_code == 401


def test_chat_endpoints_enforce_ownership():
    """追问接口：未认证 401；他人访问 404；不存在的检测 404；空消息 422；本人可读空历史"""
    with TestClient(app) as client:
        first, _ = register_and_login(client)
        second, _ = register_and_login(client)
        created = client.post(
            "/api/detections/image", headers=first,
            files={"file": ("leaf.png", png_bytes(), "image/png")},
        ).json()
        det_id = created["id"]

        # 未认证
        assert client.post(
            f"/api/detections/{det_id}/chat", json={"message": "用什么药"}
        ).status_code == 401
        assert client.get(f"/api/detections/{det_id}/chat").status_code == 401

        # 他人访问（越权必须挡住）
        assert client.post(
            f"/api/detections/{det_id}/chat", headers=second,
            json={"message": "用什么药"},
        ).status_code == 404
        assert client.get(
            f"/api/detections/{det_id}/chat", headers=second
        ).status_code == 404

        # 不存在的检测记录
        assert client.post(
            "/api/detections/does-not-exist/chat", headers=first,
            json={"message": "hi"},
        ).status_code == 404

        # 空消息
        assert client.post(
            f"/api/detections/{det_id}/chat", headers=first,
            json={"message": "   "},
        ).status_code == 422

        # 超长消息（防止 unbounded 输入把 LLM 上下文塞爆）
        assert client.post(
            f"/api/detections/{det_id}/chat", headers=first,
            json={"message": "啊" * 501},
        ).status_code == 422

        # 本人读历史：未调用过 LLM 时应返回空列表
        resp = client.get(f"/api/detections/{det_id}/chat", headers=first)
        assert resp.status_code == 200
        assert resp.json() == []


def test_statistics_aggregates_detected_classes():
    """回归：statistics 曾用 db.scalars() 查询两列，只要有一条记录就 500。

    空库时循环不执行所以测不出来，必须造一条带 predictions 的记录。
    """
    import asyncio

    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.database import engine
    from app.models.detection import Detection

    with TestClient(app) as client:
        headers, _ = register_and_login(client)
        created = client.post(
            "/api/detections/image", headers=headers,
            files={"file": ("leaf.png", png_bytes(), "image/png")},
        ).json()
        det_id = created["id"]

        preds = [
            {"class": "aphids", "confidence": 0.91},
            {"class": "aphids", "confidence": 0.72},
            {"class": "blister beetle", "confidence": 0.55},
        ]

        async def set_preds():
            async with AsyncSession(engine) as session:
                await session.execute(
                    update(Detection)
                    .where(Detection.id == det_id)
                    .values(predictions=preds)
                )
                await session.commit()

        asyncio.run(set_preds())

        resp = client.get("/api/statistics", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total_objects"] == 3
        by_name = {c["name"]: c["count"] for c in data["classes"]}
        assert by_name.get("aphids") == 2
        assert by_name.get("blister beetle") == 1


# ═══════════════════════════════════════════════════════════════
# 第四轮补充测试 T1–T6
# ═══════════════════════════════════════════════════════════════

def test_auth_me_endpoint():
    """T1: GET /api/auth/me —— 带 token 返回 200 且 username 正确；无 token 返回 401"""
    with TestClient(app) as client:
        headers, username = register_and_login(client)
        resp = client.get("/api/auth/me", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["username"] == username
        # 无 token
        assert client.get("/api/auth/me").status_code == 401


def test_feedback_endpoint():
    """T2: POST /api/detections/{id}/feedback —— 合法 good/bad 200；非法 rating 422；未认证 401；他人 404"""
    with TestClient(app) as client:
        first, _ = register_and_login(client)
        second, _ = register_and_login(client)
        created = client.post(
            "/api/detections/image", headers=first,
            files={"file": ("leaf.png", png_bytes(), "image/png")},
        ).json()
        det_id = created["id"]

        # 合法 good
        resp = client.post(f"/api/detections/{det_id}/feedback", headers=first, json={"rating": "good"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # 合法 bad（带 note）
        resp = client.post(
            f"/api/detections/{det_id}/feedback", headers=first,
            json={"rating": "bad", "note": "认错了"},
        )
        assert resp.status_code == 200

        # 非法 rating
        resp = client.post(f"/api/detections/{det_id}/feedback", headers=first, json={"rating": "awesome"})
        assert resp.status_code == 422

        # 未认证
        assert client.post(f"/api/detections/{det_id}/feedback", json={"rating": "good"}).status_code == 401

        # 他人记录
        assert client.post(
            f"/api/detections/{det_id}/feedback", headers=second, json={"rating": "good"}
        ).status_code == 404


def test_delete_all_is_scoped_to_user():
    """T3: DELETE /api/detections/all —— 返回 204；清空后列表为空；他人记录不受影响"""
    with TestClient(app) as client:
        first, _ = register_and_login(client)
        second, _ = register_and_login(client)

        # 两个用户各上传一张
        client.post("/api/detections/image", headers=first, files={"file": ("a.png", png_bytes(), "image/png")})
        client.post("/api/detections/image", headers=second, files={"file": ("b.png", png_bytes(), "image/png")})
        assert len(client.get("/api/detections", headers=first).json()) == 1
        assert len(client.get("/api/detections", headers=second).json()) == 1

        # first 清空自己的
        assert client.delete("/api/detections/all", headers=first).status_code == 204
        assert client.get("/api/detections", headers=first).json() == []
        # second 的记录不受影响
        assert len(client.get("/api/detections", headers=second).json()) == 1


def test_upload_invalid_files():
    """T4: 上传非法文件 —— text/plain → 415；空文件 → 422"""
    with TestClient(app) as client:
        headers, _ = register_and_login(client)

        # MIME 类型不支持
        resp = client.post(
            "/api/detections/image", headers=headers,
            files={"file": ("doc.txt", b"hello world", "text/plain")},
        )
        assert resp.status_code == 415

        # 空文件
        resp = client.post(
            "/api/detections/image", headers=headers,
            files={"file": ("empty.png", b"", "image/png")},
        )
        assert resp.status_code == 422


def test_list_pagination_and_filter():
    """T5: 列表分页与过滤 —— limit=1 只返回 1 条；media_type=bogus → 422；limit=9999 被夹到 100"""
    with TestClient(app) as client:
        headers, _ = register_and_login(client)
        # 上传 3 张
        for i in range(3):
            client.post(
                "/api/detections/image", headers=headers,
                files={"file": (f"leaf{i}.png", png_bytes(), "image/png")},
            )

        # limit=1
        resp = client.get("/api/detections", headers=headers, params={"limit": 1})
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        # 非法 media_type
        resp = client.get("/api/detections", headers=headers, params={"media_type": "bogus"})
        assert resp.status_code == 422

        # limit 过大被夹到 100（不报错，返回全部 3 条）
        resp = client.get("/api/detections", headers=headers, params={"limit": 9999})
        assert resp.status_code == 200
        assert len(resp.json()) == 3


def test_video_endpoint_auth():
    """T6: 视频接口鉴权 —— GET /api/videos/{不存在id} → 404；他人视频 → 404（不需要启动 Redis）"""
    with TestClient(app) as client:
        first, _ = register_and_login(client)
        second, _ = register_and_login(client)

        # 不存在的 id
        assert client.get("/api/videos/does-not-exist", headers=first).status_code == 404

        # 造一个 video 记录：提交视频时 Redis 不可用会返回 503，但记录已落库
        import os
        video_bytes = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
        resp = client.post(
            "/api/videos", headers=first,
            files={"file": ("clip.mp4", video_bytes, "video/mp4")},
        )
        # 无论 202（Redis 可用）还是 503（不可用），记录都已创建
        assert resp.status_code in (202, 503)
        # 从列表中拿到 video 类型记录的 id
        items = client.get("/api/detections", headers=first).json()
        video_items = [it for it in items if it["media_type"] == "video"]
        assert len(video_items) >= 1
        video_id = video_items[0]["id"]

        # 本人可以访问
        assert client.get(f"/api/videos/{video_id}", headers=first).status_code == 200

        # 他人访问 → 404
        assert client.get(f"/api/videos/{video_id}", headers=second).status_code == 404

        # 未认证 → 401
        assert client.get(f"/api/videos/{video_id}").status_code == 401
