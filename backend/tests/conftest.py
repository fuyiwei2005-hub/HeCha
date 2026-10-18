import asyncio
import os
import shutil
import tempfile
from pathlib import Path

import pytest


TEST_DB = Path(__file__).parent / "test.db"
TEST_DB.unlink(missing_ok=True)

# 必须用 setdefault 而不是直接赋值：pytest 由 conftest.py 在收集阶段就加载，
# 此时如果已经指向真实库（例如被其他脚本 import），直接赋值仍可能来不及。
# 这里同时把 UPLOAD_DIR / RESULT_DIR 隔离到临时目录。
_before_db = os.environ.get("DATABASE_URL")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB.as_posix()}"
assert _before_db != os.environ["DATABASE_URL"] or "test.db" in os.environ["DATABASE_URL"], (
    f"DATABASE_URL 未成功切到测试库，实际为 {os.environ['DATABASE_URL']} —— "
    "如果测试真的连了生产库，会造成数据污染，请检查环境变量设置顺序"
)

# 测试期的文件落盘目录必须隔离，否则会把图片/视频写进真实的 data/uploads、data/results，
# 而这些记录在 test.db 里，session 结束就被删掉 —— 直接制造一堆孤儿文件。
TMP_DATA = Path(tempfile.mkdtemp(prefix="pestguard_test_"))

os.environ["PRODUCT_FRONTEND"] = "legacy"
os.environ["ALLOW_MOCK_DETECTOR"] = "true"
os.environ["MODEL_PATH"] = ""
os.environ["UPLOAD_DIR"] = str(TMP_DATA / "uploads")
os.environ["RESULT_DIR"] = str(TMP_DATA / "results")

from app.core.database import engine
from app.core.rate_limit import auth_limiter, llm_limiter
from app.models import Base


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """每个测试用例前重置限流计数，避免测试间互相影响。

    llm_limiter 也要重置：它是按用户计数的 20 次/分钟，
    测试里同一个用户连续上传多张图会把它撑爆，表现为莫名其妙的 429。
    """
    auth_limiter.reset()
    llm_limiter.reset()
    yield


# 【必须随仓库分发】的运行时数据文件，缺失即视为环境错误。
# 这类文件一旦被 .gitignore 排除，干净 clone 上会「静默降级」——
# 测试大量跳过、整套看起来还是绿的，而 RAG / 寄主先验其实都没在工作。
# 所以在会话开始就明确报错，把问题挡在最前面。
REQUIRED_DATA = [
    Path(__file__).parent.parent / "data" / "host_prior.json",
    Path(__file__).parent.parent / "data" / "knowledge",
]


def pytest_sessionstart(session):
    missing = [str(p) for p in REQUIRED_DATA if not p.exists()]
    if missing:
        raise RuntimeError(
            "缺少运行时必需的数据文件，测试无法可信地运行：\n  "
            + "\n  ".join(missing)
            + "\n\n这些文件必须随仓库分发（不是构建产物、不是密钥）。\n"
            "若从 git clone 得到，请检查 .gitignore 是否整体忽略了 backend/data/。"
        )

    async def create_tables():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create_tables())


def pytest_sessionfinish(session, exitstatus):
    async def drop_tables():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(drop_tables())
    TEST_DB.unlink(missing_ok=True)
    shutil.rmtree(TMP_DATA, ignore_errors=True)
