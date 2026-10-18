"""作物上下文的 API 层集成测试。

重点是「无论用户传什么鬼东西进来，检测都不能崩，也不能少检出东西」。
mock detector 下 predictions 恒为空，所以这里主要验证接口契约与容错，
真正的重排逻辑由 tests/test_host_prior.py 覆盖。
"""
from __future__ import annotations

import io
import re
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app


def _login(client: TestClient):
    # 用 uuid 而不是 hash(str(client))：后者在不同进程/运行间不稳定，
    # 还有小概率撞号（撞上就是 register 409，测试莫名其妙地挂）。
    uname = f"croptest{uuid.uuid4().hex[:10]}"
    client.post("/api/auth/register", json={"username": uname, "password": "test12345"})
    token = client.post(
        "/api/auth/login",
        data={"username": uname, "password": "test12345"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (120, 160, 90)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_crop_endpoint_shape(client):
    r = client.get("/api/detections/crops", headers=_login(client))
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert isinstance(body["crops"], list) and body["crops"]

    for c in body["crops"]:
        assert {"key", "label", "has_prior"} <= set(c)
        has = c["has_prior"]
        assert (c["strong_count"] + c["related_count"] > 0) == has, (
            f"{c['key']} 的 has_prior 与候选数不一致"
        )

    # 下拉框至少要能选中真正起作用的作物，否则这个功能对用户等于没有
    assert any(c["has_prior"] for c in body["crops"])


@pytest.mark.parametrize(
    "crop",
    [
        None,            # 不选
        "",              # 空串
        "   ",           # 纯空白
        "榴莲",           # 清单外作物
        "水稻",           # 正常
        "x" * 500,       # 超长攻击串
        "<script>",      # 注入尝试
    ],
)
def test_detect_image_tolerates_any_crop(client, crop):
    """任何 crop 输入都必须 201 —— 作物是锦上添花，绝不能成为失败点。

    注意 crop 必须走 data=（表单字段），不能走 files=：
    一旦被当成文件上传，FastAPI 的 Form(None) 会直接 422。
    前端同样要用 formData.append('crop', value) 而不是塞 Blob。
    """
    headers = _login(client)
    data = {}
    if crop is not None:
        data["crop"] = crop
    r = client.post(
        "/api/detections/image",
        headers=headers,
        files={"file": ("leaf.png", _png(), "image/png")},
        data=data,
    )
    assert r.status_code == 201, r.text


def test_crop_is_persisted_and_returned(client):
    headers = _login(client)
    r = client.post(
        "/api/detections/image",
        headers=headers,
        files={"file": ("a.png", _png(), "image/png")},
        data={"crop": "水稻"},
    )
    assert r.status_code == 201
    assert r.json()["crop"] == "水稻"

    listed = client.get("/api/detections", headers=headers).json()
    assert listed[0]["crop"] == "水稻"


def test_unknown_crop_is_dropped_not_stored(client):
    """清单外的作物不入库 —— 存进去会让后续统计与评测集被脏数据污染。"""
    headers = _login(client)
    r = client.post(
        "/api/detections/image",
        headers=headers,
        files={"file": ("b.png", _png(), "image/png")},
        data={"crop": "榴莲"},
    )
    assert r.status_code == 201
    assert r.json()["crop"] is None


def test_overlong_crop_is_truncated(client):
    """超长输入必须被截断，否则超过 String(32) 会直接 500。"""
    headers = _login(client)
    r = client.post(
        "/api/detections/image",
        headers=headers,
        files={"file": ("c.png", _png(), "image/png")},
        data={"crop": "水" * 500},
    )
    assert r.status_code == 201
    crop = r.json()["crop"]
    assert crop is None or len(crop) <= 32


def test_crop_requires_auth():
    """未登录不能调作物接口 —— 别给匿名请求暴露内部数据。"""
    with TestClient(app) as c:
        assert c.get("/api/detections/crops").status_code in (401, 403)
