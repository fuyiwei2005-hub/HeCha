"""schema 自检的测试：缺列必须能被报出来，且不能影响启动。"""
from __future__ import annotations

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.schema_check import check_schema
from app.models.base import Base
from app.models.detection import Detection
from app.models.user import User

# 0001 初始迁移建出来的 Detection 结构（缺 analysis/references/crop/video_meta）
LEGACY_DETECTIONS = """
CREATE TABLE detections (
    id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER NOT NULL,
    media_type VARCHAR(16) NOT NULL,
    original_name VARCHAR(255),
    stored_name VARCHAR(255),
    predictions JSON,
    result_path VARCHAR(255),
    status VARCHAR(16) NOT NULL,
    error TEXT,
    created_at DATETIME NOT NULL
)
"""

LEGACY_USERS = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(64) UNIQUE,
    email VARCHAR(320) UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME
)
"""

# chat_messages 由 0003 引入，一并建出来，避免干扰被测的表
LEGACY_CHAT = """
CREATE TABLE chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detection_id VARCHAR(36) NOT NULL,
    user_id INTEGER NOT NULL,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    created_at DATETIME
)
"""


@pytest_asyncio.fixture()
async def legacy_engine() -> AsyncEngine:
    """造一个「只跑了 0001」的空库，模拟没升级的服务器。"""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.execute(sa.text(LEGACY_USERS))
        await conn.execute(sa.text(LEGACY_DETECTIONS))
        await conn.execute(sa.text(LEGACY_CHAT))
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_detects_missing_columns(legacy_engine):
    """缺列必须被报出来，且点名是哪些列。"""
    report = await check_schema(legacy_engine)
    assert report["ok"] is False
    assert "detections" in report["missing"]

    missing = report["missing"]["detections"]
    for col in ("analysis", "references", "crop", "video_meta"):
        assert col in missing, f"应报告缺失列 {col}"


@pytest.mark.asyncio
async def test_reports_table_missing_entirely(legacy_engine):
    """整表缺失时也要报，而不是静默通过。"""
    async with legacy_engine.begin() as conn:
        await conn.execute(sa.text("DROP TABLE detections"))
    report = await check_schema(legacy_engine)
    assert report["ok"] is False
    assert "detections" in report["missing"]


@pytest.mark.asyncio
async def test_passes_on_matching_schema():
    """结构完整时必须返回 ok —— 不能误报，否则每次启动都刷警告。"""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    report = await check_schema(eng)
    assert report["ok"] is True
    assert report["missing"] == {}
    await eng.dispose()


@pytest.mark.asyncio
async def test_never_raises_on_broken_db():
    """连不上数据库时自检不能抛异常，否则会把服务拦在启动之外。"""
    eng = create_async_engine("sqlite+aiosqlite:////nonexistent-dir/x.db")
    report = await check_schema(eng)
    # 报错也要返回 ok=True（放行），错误信息走 error 字段
    assert report["ok"] is True
    await eng.dispose()


def test_model_columns_are_the_source_of_truth():
    """守住前提：模型里这些列必须存在，否则上面的测试在测一个错误的假设。"""
    cols = set(Detection.__table__.columns.keys())
    for col in ("analysis", "references", "crop", "video_meta"):
        assert col in cols
    assert "username" in set(User.__table__.columns.keys())
