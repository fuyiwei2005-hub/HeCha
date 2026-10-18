"""校验：ORM 模型声明的每张表/每个字段，都必须有对应的 alembic 迁移产物。

用法：python tools/check_migrations.py

做法：在**空库**上跑完所有迁移，再把得到的结构与 ORM 模型声明比对。
任何差异都意味着「全新环境部署后相关接口必然 500」

这类缺陷在开发机上永远看不见：开发库通常是被长期的试跑喂出来的，
结构恰好是齐全的；只有全新的部署才会暴露「模型改了但没写迁移」。
"""
from __future__ import annotations

import os
import sys
import tempfile

# 这个脚本被测试用例以管道方式调用（capture_output=True），
# 此时 Python 会退回 locale 编码 —— Windows 上是 cp1252，
# 下面那些中文 print 会直接 UnicodeEncodeError，迁移代码一行都跑不到，
# 而测试看到的却是"迁移不一致"。这里强制 UTF-8，与平台无关。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError, OSError):  # 极老解释器/已重定向且不支持时忽略
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
os.chdir(BACKEND)
sys.path.insert(0, os.getcwd())

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, inspect  # noqa: E402

import app.models  # noqa: F401,E402  —— 注册全部模型，否则 metadata 不全
from app.models.base import Base  # noqa: E402


def main() -> int:
    tmpdir = tempfile.mkdtemp(prefix="migcheck_")
    db = os.path.join(tmpdir, "check.db")
    async_url = f"sqlite+aiosqlite:///{db}"  # 迁移走异步引擎（env.py 的要求）
    sync_url = f"sqlite:///{db}"             # 检查走同步引擎，避开 greenlet

    # 关键：alembic/env.py 第 13 行会用 get_settings().database_url
    # 强行覆盖 sqlalchemy.url —— 必须改环境变量本身才能指向临时库，
    # 否则会把迁移跑到你本地正式的 pestguard.db 上。
    os.environ["DATABASE_URL"] = async_url

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", async_url)
    cfg.set_main_option("script_location", "alembic")

    print("在空库上执行全部迁移…")
    command.upgrade(cfg, "head")

    problems: list[str] = []
    eng = create_engine(sync_url)
    try:
        insp = inspect(eng)
        migrated_tables = set(insp.get_table_names())

        print("\n比对「模型声明」与「迁移产物」：\n")
        for tname, table in Base.metadata.tables.items():
            if tname not in migrated_tables:
                problems.append(f"表 {tname}：模型已声明，但迁移从未创建")
                print(f"  X  表 {tname}：迁移缺失")
                continue

            have = {c["name"] for c in insp.get_columns(tname)}
            want = {c.name for c in table.columns}
            missing = sorted(want - have)
            if missing:
                problems.append(f"表 {tname} 缺列：{', '.join(missing)}")
                print(f"  X  表 {tname} 缺列：{', '.join(missing)}")
            else:
                print(f"  OK {tname} ({len(want)} 列)")

        for t in sorted(migrated_tables - set(Base.metadata.tables)):
            if t != "alembic_version":
                print(f"  .  {t}：迁移表存在但模型未声明（自行确认是否为历史遗留）")
    finally:
        eng.dispose()

    for f in os.listdir(tmpdir):
        try:
            os.remove(os.path.join(tmpdir, f))
        except OSError:
            pass
    try:
        os.rmdir(tmpdir)
    except OSError:
        pass

    print()
    if problems:
        print(f"发现 {len(problems)} 处不一致 —— 新环境部署后接口会 500：")
        for p in problems:
            print(f"  - {p}")
        print("\n请为上述变更补写 alembic 迁移脚本。")
        return 1
    print("全部一致：全新环境执行 alembic upgrade head 后结构即完整。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
