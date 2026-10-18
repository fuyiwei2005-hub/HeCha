#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PestGuard 项目快照工具 —— 动手改代码之前先跑一次。

为什么要有这个：项目 .git 是空仓库（0 个 tracked 文件），改坏了没法用版本控制回滚。
所以每次「要动代码之前」，先用本脚本做一份完整快照，再开工。

快照内容：
  - 项目全部源码 / 文档 / 数据文件（排除可重建的依赖环境与缓存）
  - SQLite 数据库单独复制一份（DB 最容易被误写）
  - pip freeze 固化当前 Python 环境依赖版本（重装可精确复现）
  - MANIFEST.json 记录文件清单与 SHA1，便于事后核对/回滚比对

用法：
    python tools/backup_project.py                 # 快照到默认目录
    python tools/backup_project.py --name before-refactor   # 自定义快照名
    python tools/backup_project.py --list          # 查看已有快照
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP_HOME = Path(r"D:\pestguard_备份")

# 可重建的依赖环境 / 缓存 —— 不进快照（它们加起来近 2GB，坏了重装即可）
# _backups / .pt_tmp 是本工具与训练脚本自己产生的中间产物目录。
EXCLUDE_DIRS = {
    ".venv", "node_modules", "__pycache__", ".pytest_cache",
    ".git", ".idea", "dist", ".cache", ".slidep",
    "_backups", ".pt_tmp",
}
# 体积大但可由工具重新生成的产物
#
# 密钥与个人数据必须排除（.gitignore 只管 git，不管本脚本的复制行为）：
#   - .env* 里是真实的 SECRET_KEY / DEEPSEEK_API_KEY，拷进备份目录等于把密钥
#     明文复制到 D:\pestguard_备份\，而备份目录往往不在任何加密盘里；
#   - *.db 及其 -wal/-shm/-journal 旁路文件、*.bak 是含 password_hash、
#     聊天正文的用户数据副本。
#     main() 里已有一段「DB 单独复制一份到快照根目录」的逻辑，它不走 os.walk，
#     不受本规则影响；这里排除的是散落在项目树里的额外副本。
# 注意 str.endswith 是元组匹配，"backend/.env" 这类无扩展名文件
# 也能被 (".env",) 命中（判断依据是文件名部分，不是相对路径）。
#
# 这几条必须与 .gitignore(15-20 行) 和 backend/.dockerignore(31-36 行) 严格对齐：
# SQLite 在 WAL 模式下的 -wal / -shm / -journal 同样承载已提交数据页
# （用户、密码哈希、聊天正文），漏掉任何一条等于把数据库交出去。
# 注意它们的后缀是 "-shm"/"-journal"/"-wal" 而非 ".db"，endswith(".db") 匹配不到。
EXCLUDE_FILES_PATTERN = (
    ".tsbuildinfo",
    ".env", ".env.local", ".env.production",
    ".db", ".db-wal", ".db-shm", ".db-journal",
    ".sqlite-wal", ".sqlite-shm",
    ".bak",
)
# endswith 抓不到带时间戳的库备份：真实文件名形如
# pestguard.db.bak_20261005_120155，以时间戳结尾而非 ".bak"结尾。
# EXCLUDE_DIRS 里的 "_backups" 只挡得住目录内的文件；
# 万一这类副本被放到 _backups/ 之外，仍会漏。补一条精确的子串判断，
# 用 ".db.bak_" 而非泛化的 "bak" —— 后者会误伤 backup.py 之类的正常源码。
EXCLUDE_FILE_SUBSTRINGS = (".db.bak_",)
EXCLUDE_PATH_PARTS = {"参赛打包"}


def sha1(p: Path, chunk=1 << 20) -> str:
    h = hashlib.sha1()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def should_skip(rel_parts: set, name: str) -> bool:
    """判断一个目录名是否应被排除（os.walk 的 dirnames 过滤用）。"""
    if name in EXCLUDE_DIRS:
        return True
    return bool(set(rel_parts) & EXCLUDE_PATH_PARTS)


def should_skip_file(name: str) -> bool:
    """判断一个文件名是否应被排除（os.walk 的 filenames 过滤用）。

    分两步判：先endswith 后缀，再查子串 —— 因为带时间戳的库备份
    （pestguard.db.bak_20261005_120155）既不以 .bak 结尾，也匹配不到通配，
    只有子串判断能拦住。抽成独立函数是为了让这两个规则只有一处实现，
    避免改一处漏一处。
    """
    if name.endswith(EXCLUDE_FILES_PATTERN):
        return True
    return any(s in name for s in EXCLUDE_FILE_SUBSTRINGS)


def main():
    ap = argparse.ArgumentParser(description="PestGuard 项目快照")
    ap.add_argument("--name", default="", help="快照名，默认是时间戳")
    ap.add_argument("--out", default=str(BACKUP_HOME), help="快照根目录")
    ap.add_argument("--list", action="store_true", help="列出已有快照")
    args = ap.parse_args()

    home = Path(args.out)
    if args.list:
        if not home.exists():
            print("还没有任何快照:", home)
            return 0
        snaps = sorted(p for p in home.iterdir() if p.is_dir())
        print("已有快照 %d 份（%s）:" % (len(snaps), home))
        total = 0
        for s in snaps:
            sz = sum(f.stat().st_size for dp, dn, fns in os.walk(s) for fn in fns
                     for f in [Path(dp) / fn] if f.exists())
            total += sz
            mf = s / "MANIFEST.json"
            n = "?"
            if mf.exists():
                try:
                    n = json.loads(mf.read_text(encoding="utf-8")).get("file_count", "?")
                except Exception:
                    pass
            print("  %-34s %8.1f MB  %s 个文件" % (s.name, sz / 1024 / 1024, n))
        print("  合计 %.1f MB" % (total / 1024 / 1024))
        return 0

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap_name = f"{stamp}_{args.name}" if args.name else stamp
    dst_root = home / snap_name
    dst = dst_root / "pestguard"
    if dst.exists():
        print("快照已存在，跳过:", dst)
        return 1

    dst.mkdir(parents=True, exist_ok=True)
    print("=" * 74)
    print("PestGuard 项目快照")
    print("源  : %s" % ROOT)
    print("目标: %s" % dst_root)
    print("=" * 74)

    files = []
    total = 0
    errors = []

    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel_dir = Path(dirpath).relative_to(ROOT)
        parts = set(rel_dir.parts)
        dirnames[:] = [d for d in dirnames if not should_skip(parts, d)]
        for fn in filenames:
            if should_skip_file(fn):
                continue
            src = Path(dirpath) / fn
            rel = src.relative_to(ROOT)
            target = dst / rel
            try:
                if not src.exists():
                    continue
                if not src.is_file():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
                sz = src.stat().st_size
                total += sz
                files.append({"path": str(rel).replace("\\", "/"), "size": sz,
                              "sha1": sha1(src)})
            except Exception as e:
                errors.append((str(rel), repr(e)))

    # 数据库单独放一份快照根目录，方便一眼找到（DB 最怕误写）
    db_notes = []
    for db_rel in ("backend/pestguard.db",):
        db = ROOT / db_rel
        if db.exists():
            target = dst_root / "DB_pestguard.db"
            try:
                shutil.copy2(db, target)
                db_notes.append("已单独备份 → %s (%.0f KB)"
                                % (target.name, target.stat().st_size / 1024))
            except Exception as e:
                errors.append((db_rel, repr(e)))

    # 固化依赖版本
    venv_py = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
    freeze_ok = False
    if venv_py.exists():
        try:
            out = subprocess.run([str(venv_py), "-m", "pip", "freeze"],
                                 capture_output=True, text=True, timeout=120)
            (dst_root / "pip_freeze.txt").write_text(out.stdout, encoding="utf-8")
            freeze_ok = out.returncode == 0
        except Exception as e:
            errors.append(("pip freeze", repr(e)))

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(ROOT),
        "file_count": len(files),
        "total_bytes": total,
        "total_mb": round(total / 1024 / 1024, 2),
        "files": files,
        "note": args.name or "标准快照",
    }
    (dst_root / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n快照完成")
    print("  文件数  : %d" % len(files))
    print("  总大小  : %.1f MB" % (total / 1024 / 1024))
    for n in db_notes:
        print("  %s" % n)
    print("  依赖清单: %s" % ("pip_freeze.txt 已生成" if freeze_ok else "（未生成）"))
    print("  清单文件: MANIFEST.json（含每个文件 SHA1，可核对/回滚）")
    if errors:
        print("\n[失败 %d 项]" % len(errors))
        for p, e in errors[:10]:
            print("  -", p, e)
    print("\n回滚办法：用资源管理器打开 %s，按需拷回覆盖。" % dst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
