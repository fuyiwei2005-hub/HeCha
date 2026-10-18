"""数据库连接的方言相关行为。

这里的用例都对应**真实踩过的坑**，而且是"本机永远看不见"的那种：

1. PRAGMA 语句不是合法的 PostgreSQL 语法，却曾经被无条件下发到每一条连接上。
   本地/线上实际用 SQLite，所以一直没暴露；而 docker-compose 配的是
   postgresql+asyncpg，等于整条 Postgres 部署路径都是坏的。
   这条用例把"非 SQLite 时绝不碰 PRAGMA"钉死。

2. 运行时数据文件（先验表 / 知识库）必须随仓库分发，缺了要让测试响亮地失败，
   而不是静默 skip 掉一大批用例。
"""
from __future__ import annotations

from pathlib import Path

import pytest


# ── 1. PRAGMA 只对 SQLite 执行 ─────────────────────────────────────────

class _FakeCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.closed = False

    def execute(self, sql: str, *args, **kwargs):
        self.statements.append(sql)

    def close(self) -> None:
        self.closed = True


class _FakeConnection:
    """只实现 dbapi 连接里被用到的那一小部分。"""

    def __init__(self) -> None:
        self.cursor_obj = _FakeCursor()

    def cursor(self) -> _FakeCursor:
        return self.cursor_obj


def test_pragma_is_not_sent_to_postgres(monkeypatch):
    """Postgres 连接上不允许出现任何 PRAGMA 语句。

    这是 docker-compose 的默认路径，坏了就整条部署链路不可用。
    """
    from app.core import database

    monkeypatch.setattr(
        database.settings, "database_url",
        "postgresql+asyncpg://pestguard:pw@db:5432/pestguard", raising=False,
    )
    conn = _FakeConnection()
    database._set_sqlite_pragma(conn, None)

    assert conn.cursor_obj.statements == [], (
        "非 SQLite 连接上不应执行任何 PRAGMA；"
        f"实际下发了 {conn.cursor_obj.statements}"
    )
    # 连 cursor 都不该被取出来，避免留下未关闭的游标
    assert conn.cursor_obj.closed is False


def test_pragma_is_applied_on_sqlite(monkeypatch):
    """SQLite 上必须把 WAL / busy_timeout / 外键都设上，否则并发写会报 locked。"""
    from app.core import database

    monkeypatch.setattr(
        database.settings, "database_url",
        "sqlite+aiosqlite:///./whatever.db", raising=False,
    )
    conn = _FakeConnection()
    database._set_sqlite_pragma(conn, None)

    joined = " ".join(conn.cursor_obj.statements).upper()
    assert "PRAGMA FOREIGN_KEYS=ON" in joined
    assert "JOURNAL_MODE=WAL" in joined
    assert "BUSY_TIMEOUT" in joined
    assert conn.cursor_obj.closed is True


# ── 2. 必需的运行时数据文件 ────────────────────────────────────────────

BACKEND_DIR = Path(__file__).resolve().parent.parent

# 与 tests/conftest.py 的 REQUIRED_DATA 保持一致。
# 这里刻意**不** import conftest —— conftest 是 pytest 的插件模块，
# 直接 import 会被再执行一次（包括它顶部的建库/删库副作用）。
REQUIRED_RUNTIME_DATA = [
    BACKEND_DIR / "data" / "host_prior.json",
    BACKEND_DIR / "data" / "knowledge" / "pests_cereal.json",
    BACKEND_DIR / "data" / "knowledge" / "pests_fruit.json",
    BACKEND_DIR / "data" / "knowledge" / "pesticide.json",
    BACKEND_DIR / "data" / "knowledge" / "practice.json",
]


def test_required_runtime_data_is_present():
    """先验表与知识库是运行时必需文件，必须能在仓库里找到。

    历史事故：.gitignore 里整体忽略了 backend/data/，于是干净 clone 上
    host_prior 相关 33 个用例全部静默跳过、RAG 用例直接失败，
    而 deploy/README.md 恰恰推荐用 git clone 部署。
    """
    missing = [str(p) for p in REQUIRED_RUNTIME_DATA if not p.exists()]
    assert not missing, (
        "缺少运行时必需的数据文件：" + ", ".join(missing) + "\n"
        "这些文件必须随仓库分发（不是构建产物）；"
        "请检查 .gitignore 是否整体忽略了 backend/data/。"
    )


def test_knowledge_base_files_are_non_trivial():
    """知识库 JSON 不能是空文件 —— 空文件会让 RAG 静默降级而不是报错。"""
    kb_dir = BACKEND_DIR / "data" / "knowledge"
    jsons = sorted(kb_dir.glob("*.json"))
    assert jsons, f"知识库目录下没有任何 JSON：{kb_dir}"
    tiny = [p.name for p in jsons if p.stat().st_size < 1024]
    assert not tiny, f"以下知识库文件过小，疑似被截断或占位：{tiny}"


def test_host_prior_table_is_non_trivial():
    prior = BACKEND_DIR / "data" / "host_prior.json"
    assert prior.stat().st_size > 4096, f"先验表过小，疑似不完整：{prior}"


# ── 3. 大模型接口的按用户配额 ──────────────────────────────────────────

def test_llm_quota_is_per_user_not_per_ip():
    """配额按 user_id 计，不按 IP。

    按 IP 会在同一出口（实验室/公司 NAT）下误伤同事；
    而滥用者换个 IP 就能绕过。
    """
    import asyncio

    from app.core.rate_limit import RateLimiter, llm_limiter

    limiter = RateLimiter(max_requests=3, window_seconds=60, name="llmtest")

    async def run() -> None:
        for _ in range(3):
            await limiter.check_async("u1")
        # 同一个用户超额 -> 429
        with pytest.raises(Exception) as exc:
            await limiter.check_async("u1")
        assert getattr(exc.value, "status_code", None) == 429
        # 另一个用户不受影响
        await limiter.check_async("u2")

    asyncio.run(run())
    assert llm_limiter.max_requests >= 5, "配额过小会误伤正常演示"


def test_llm_endpoints_enforce_quota(monkeypatch):
    """纯识别不消耗 AI 配额，追问仍受限制；后台解读在任务测试中覆盖。"""
    import io

    from fastapi.testclient import TestClient
    from PIL import Image

    from app.core.rate_limit import llm_limiter
    from app.main import app

    def png() -> bytes:
        out = io.BytesIO()
        Image.new("RGB", (32, 32), "green").save(out, "PNG")
        return out.getvalue()

    # 把配额压到 1，耗尽后仍允许本地图片识别。
    monkeypatch.setattr(llm_limiter, "max_requests", 1)
    llm_limiter.reset()
    try:
        with TestClient(app) as client:
            import uuid
            uname = f"quotatest{uuid.uuid4().hex[:8]}"
            client.post("/api/auth/register",
                        json={"username": uname, "password": "test12345"})
            token = client.post("/api/auth/login",
                                data={"username": uname, "password": "test12345"}
                                ).json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            first = client.post(
                "/api/detections/image", headers=headers,
                files={"file": ("a.png", png(), "image/png")},
            )
            assert first.status_code == 201, first.text

            second = client.post(
                "/api/detections/image", headers=headers,
                files={"file": ("b.png", png(), "image/png")},
            )
            assert second.status_code == 201
            assert second.json()["status"] == "completed"
            import asyncio
            from app.core.rate_limit import check_llm_quota
            user_id = client.get('/api/auth/me', headers=headers).json()['id']
            asyncio.run(check_llm_quota(user_id))
            chat = client.post(f"/api/detections/{first.json()['id']}/chat", headers=headers,
                               json={"message": "如何防治？"})
            assert chat.status_code == 429
    finally:
        llm_limiter.reset()
