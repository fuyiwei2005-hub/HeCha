#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PestGuard 账号清理工具

背景：开发调试/截图脚本会自动注册一批临时账号，攒久了库里全是垃圾账号。
本工具按「白名单保留 + 其余删除」的方式清理，删除前自动备份数据库。

设计要点：
  - 默认 dry-run，只有加 --apply 才真正删
  - 删除前自动备份 pestguard.db → _backups/pestguard.db.bak_<时间戳>
  - 先删关联数据（detections / chat_messages）再删 users：
    SQLite 默认不开启外键约束，直接删 users 会留下孤儿检测记录
  - 同时清理这些账号在 data/uploads、data/results 里实际占用的文件

用法：
    python tools/delete_accounts.py                       # 预览（保留 demo）
    python tools/delete_accounts.py --keep demo,666       # 预览，额外保留 666
    python tools/delete_accounts.py --all-except demo     # 预览，除 demo 外全删
    python tools/delete_accounts.py --apply               # 真正执行（需确认）
"""

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
DB = BACKEND / "pestguard.db"
BACKUP_DIR = BACKEND / "_backups"
UPLOAD_DIR = BACKEND / "data" / "uploads"
RESULT_DIR = BACKEND / "data" / "results"


def list_users(con):
    """注意：计数必须用独立游标。在迭代 cursor 的结果集时，若用同一个 cursor
    再执行 SQL，上一个结果集会被重置，外层循环会静默只走一次（真实踩过）。"""
    main_cur = con.cursor()
    cnt_cur = con.cursor()
    cols = [r[1] for r in main_cur.execute("PRAGMA table_info(users)")]
    idx = {c: i for i, c in enumerate(cols)}
    rows = main_cur.execute("SELECT * FROM users ORDER BY id").fetchall()
    out = []
    for row in rows:
        uid = row[idx["id"]]
        try:
            n_det = cnt_cur.execute(
                "SELECT COUNT(*) FROM detections WHERE user_id=?", (uid,)).fetchone()[0]
        except sqlite3.Error:
            n_det = 0
        out.append({
            "id": uid,
            "username": row[idx.get("username", 0)] if "username" in idx else None,
            "email": row[idx["email"]] if "email" in idx else None,
            "created_at": row[idx["created_at"]] if "created_at" in idx else None,
            "detections": n_det,
        })
    return out


def files_of_users(con, uids):
    """找出这些账号在 uploads / results 里实际占用的文件名。"""
    if not uids:
        return set()
    cur = con.cursor()
    q = ",".join("?" * len(uids))
    names = set()
    for sql in (f"SELECT stored_name FROM detections WHERE user_id IN ({q})",
                f"SELECT result_path FROM detections WHERE user_id IN ({q})"):
        try:
            for r in cur.execute(sql, uids):
                if r[0]:
                    names.add(Path(r[0]).name)
        except sqlite3.Error:
            pass
    return names


def main():
    ap = argparse.ArgumentParser(description="清理 PestGuard 历史/临时账号")
    ap.add_argument("--keep", default="demo",
                    help="保留的用户名，逗号分隔（默认 demo）")
    ap.add_argument("--apply", action="store_true",
                    help="真正执行删除；不加则只预览")
    ap.add_argument("--with-detections", action="store_true",
                    help="被删账号有检测记录时也照删（默认仍需确认）")
    args = ap.parse_args()

    if not DB.exists():
        print("找不到数据库:", DB)
        return 1

    keep = {s.strip() for s in args.keep.split(",") if s.strip()}
    con = sqlite3.connect(str(DB))
    users = list_users(con)

    to_delete = [u for u in users if (u["username"] or "") not in keep]
    to_keep = [u for u in users if (u["username"] or "") in keep]

    print("=" * 76)
    print("PestGuard 账号清理  (dry-run)" if not args.apply else "PestGuard 账号清理  (执行模式)")
    print("数据库:", DB)
    print("=" * 76)

    print("\n[保留] %d 个" % len(to_keep))
    for u in to_keep:
        print("   id=%-3s %-20s %-24s %s  %d 条检测"
              % (u["id"], u["username"], u["email"] or "-", u["created_at"], u["detections"]))

    print("\n[删除] %d 个" % len(to_delete))
    total_det = 0
    for u in to_delete:
        total_det += u["detections"]
        print("   id=%-3s %-20s %-24s %s  %d 条检测"
              % (u["id"], u["username"], u["email"] or "-", u["created_at"], u["detections"]))
    print("\n   合计将连带删除 %d 条检测记录" % total_det)

    uids = [u["id"] for u in to_delete]
    files = files_of_users(con, uids)
    print("   关联文件 %d 个（uploads/results 中的图片视频）" % len(files))

    if not to_delete:
        print("\n没有需要删除的账号。")
        con.close()
        return 0

    if not args.apply:
        print("\n[预览模式] 未做任何改动。确认无误后加 --apply 执行。")
        con.close()
        return 0

    if total_det > 0 and not args.with_detections:
        print("\n将连带删除 %d 条检测记录。若确认，再加参数 --with-detections。" % total_det)
        con.close()
        return 1

    # 备份
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = BACKUP_DIR / f"pestguard.db.bak_{stamp}"
    con.close()
    shutil.copy2(DB, bak)
    print("\n已备份 →", bak)

    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    q = ",".join("?" * len(uids))
    # chat_messages 没有 user_id 列，只能经 detections 间接关联；
    # 且必须先删消息再删检测 —— 否则子查询拿不到父记录。
    n1 = cur.execute(
        f"DELETE FROM chat_messages WHERE detection_id IN "
        f"(SELECT id FROM detections WHERE user_id IN ({q}))", uids,
    ).rowcount
    n2 = cur.execute(f"DELETE FROM detections WHERE user_id IN ({q})", uids).rowcount
    n3 = cur.execute(f"DELETE FROM users WHERE id IN ({q})", uids).rowcount
    con.commit()
    print("已删：users=%d  detections=%d  chat_messages=%d" % (n3, n2, n1))

    # 清文件
    removed = 0
    for d in (UPLOAD_DIR, RESULT_DIR):
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if f.is_file() and f.name in files:
                try:
                    f.unlink()
                    removed += 1
                except OSError as e:
                    print("  文件删除失败:", f.name, e)
    print("已删关联文件 %d 个" % removed)

    con.close()
    print("\n完成。回滚办法：用上面的备份文件覆盖回 pestguard.db。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
