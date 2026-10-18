"""落盘文件与数据库记录的一致性。

事故回顾：图片检测先把原图和结果图写到磁盘，再调 LLM、最后 commit。
只要中间任何一步抛异常，事务回滚、记录消失，两张图却留在磁盘上——
实测一次 LLM 报错就泄漏 6 个文件 / 2MB，久而久之 uploads 目录只增不减。
"""
import io
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import get_settings
from app.main import app
from app.services import llm as llm_module


def _file_count(directory: Path) -> int:
    return len([p for p in directory.glob("*") if p.is_file()])


def png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (32, 32), "green").save(output, "PNG")
    return output.getvalue()


def register_and_login(client: TestClient) -> dict[str, str]:
    username = f"user_{uuid4().hex[:16]}"
    password = "A-secure-test-password-123"
    assert client.post(
        "/api/auth/register", json={"username": username, "password": password}
    ).status_code == 201
    response = client.post("/api/auth/login", data={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_failure_after_file_write_leaves_no_orphan_files(monkeypatch):
    """原图和结果图已经落盘、但记录还没 commit 时出错 —— 两张图必须被清掉。

    触发点选在 uuid4（生成记录主键）：它在写盘之后、commit 之前抛异常，
    正好命中「事务回滚但文件残留」这条路径。
    注意不能用 llm.analyze 来触发了——analyze 现在整体兜底降级，不会再把异常抛上来。
    """
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    result_dir = Path(settings.result_dir)

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.services.image_detection.uuid4", boom)

    before_uploads = _file_count(upload_dir)
    before_results = _file_count(result_dir)

    # raise_server_exceptions=False：让异常走 FastAPI 的正常 500 路径，
    # 而不是在测试里直接抛出——我们要验证的是服务端返回后的磁盘状态
    with TestClient(app, raise_server_exceptions=False) as client:
        headers = register_and_login(client)
        response = client.post(
            "/api/detections/image",
            headers=headers,
            files={"file": ("boom.png", png_bytes(), "image/png")},
        )
        assert response.status_code == 500

    assert _file_count(upload_dir) == before_uploads, "上传目录出现孤儿文件"
    assert _file_count(result_dir) == before_results, "结果目录出现孤儿文件"


def test_llm_error_degrades_instead_of_500(monkeypatch):
    """LLM 是可选增强：它自己崩了也不能让整单检测失败。"""

    async def boom(*_args, **_kwargs):
        raise RuntimeError("DeepSeek down")

    monkeypatch.setattr(llm_module.llm, "_analyze_inner", boom)

    with TestClient(app) as client:
        headers = register_and_login(client)
        response = client.post(
            "/api/detections/image",
            headers=headers,
            files={"file": ("ok.png", png_bytes(), "image/png")},
        )
        assert response.status_code == 201
        assert response.json()["status"] == "completed"
