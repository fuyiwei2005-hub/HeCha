"""防止「模型改了但没写 alembic 迁移」再次发生。

上次事故：给 Detection 加了 feedback / feedback_note 两个字段，
却漏了迁移脚本。开发机上一切正常（库早就被各个测试喂全了），
部署到新服务器就 no such column -> 接口 500，
而 health 检查完全发现不了。
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.slow
def test_migrations_produce_complete_schema():
    """在空库上跑完所有迁移后，结构必须与 ORM 模型完全一致。"""
    proc = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(BACKEND), "tools",
                                      "check_migrations.py")],
        cwd=BACKEND, capture_output=True, text=True, timeout=300,
        # 子进程 stdout 是管道，Python 会退化成 locale 编码（Windows 上是 cp1252），
        # 而 check_migrations.py 里 print 的是中文 —— 直接 UnicodeEncodeError，
        # 迁移代码一行都没跑到。这两行把编码钉死。
        encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert proc.returncode == 0, (
        "迁移产物与 ORM 模型不一致 —— 新环境部署会失败。\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr[-2000:]}"
    )


def test_every_model_column_is_covered_by_some_migration():
    """轻量检查：模型里每张表都至少被某个迁移脚本提到过。

    不全量跑迁移（慢），但能挡住「整表忘了写迁移」这种最粗心的错误。
    列级差异由上面那个用例在 CI 里把关。
    """
    versions_dir = os.path.join(BACKEND, "alembic", "versions")
    scripts = []
    for fn in os.listdir(versions_dir):
        if fn.endswith(".py"):
            with open(os.path.join(versions_dir, fn), encoding="utf-8") as f:
                scripts.append((fn, f.read()))

    assert scripts, "alembic/versions 下没有任何迁移脚本"

    from app.models.base import Base

    # 必须在 alembic 的 📁 文本里出现 create_table("表名") 或被
    # add_column/drop_column/op.alter_column 提及
    for tname in Base.metadata.tables:
        hit = [fn for fn, body in scripts if f'"{tname}"' in body or f"'{tname}'" in body]
        assert hit, (
            f"表 {tname} 在 ORM 模型中已声明，但没有任何迁移脚本提及它 —— "
            f"新环境建不出这张表。"
        )
