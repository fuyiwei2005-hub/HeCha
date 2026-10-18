"""数据一致性自检：检测记录 <-> 磁盘文件。

用法：
    python tools/check_data.py            # 只报告
    python tools/check_data.py --fix      # 修复：删掉失效记录 + 清掉孤儿文件
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.chdir(Path(__file__).resolve().parents[1])

from app.core.config import get_settings  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="删除失效记录与孤儿文件")
    args = ap.parse_args()

    s = get_settings()
    db_path = s.database_url.split("///")[-1]
    up_dir, res_dir = Path(s.upload_dir), Path(s.result_dir)

    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("SELECT id, media_type, original_name, stored_name, result_path, created_at "
                "FROM detections ORDER BY created_at")
    rows = cur.fetchall()

    broken, alive = [], []
    for did, mt, name, sn, rp, ca in rows:
        miss = []
        # 视频源文件在处理成功后会被 worker 主动删除（video.py 的 finally），
        # 这是设计行为，不是数据损坏 —— 只有 result 缺失才算真问题。
        check_upload = not (mt == "video")
        if check_upload and sn and not (up_dir / sn).is_file():
            miss.append("upload")
        if rp and not (res_dir / rp).is_file():
            miss.append("result")
        if miss:
            broken.append((did, mt, name, sn, rp, ca, miss))
        else:
            alive.append((did, mt, name, sn, rp, ca, miss))

    db_files = set()
    for _, _, _, sn, rp, _ in [(r[0], r[1], r[2], r[3], r[4], r[5]) for r in rows]:
        if sn:
            db_files.add(sn)
        if rp:
            db_files.add(rp)
    orphans = [p for d in (up_dir, res_dir) if d.is_dir()
               for p in d.iterdir() if p.is_file() and p.name not in db_files]

    print(f"数据库: {db_path}")
    print(f"检测记录: {len(rows)} 条 | 正常: {len(alive)} | 文件缺失: {len(broken)}")
    print("（注：视频的 upload 源文件在处理成功后被 worker 主动删除，属正常，不计入缺失）")
    for did, mt, name, sn, rp, ca, miss in broken:
        print(f"  [BROKEN] {did[:8]}  {mt:6s} {name[:28]:28s} 缺: {','.join(miss)}  {ca}")
    print(f"孤儿文件: {len(orphans)} 个 "
          f"({sum(p.stat().st_size for p in orphans)/1024:.1f} KB)")
    for p in orphans[:20]:
        print(f"  [ORPHAN] {p}")

    if not args.fix:
        print("\n（只读模式。加 --fix 才会删除。）")
        return 1 if broken or orphans else 0

    # 加 --fix 时二次确认：这两个动作都会删数据库记录，属不可逆操作
    if broken:
        print(f"\n即将删除 {len(broken)} 条「文件已缺失」的检测记录及其聊天记录：")
        for did, mt, name, _, _, _, miss in broken:
            print(f"  - {did[:8]} {mt} {name} (缺 {','.join(miss)})")
    if orphans:
        print(f"即将删除 {len(orphans)} 个无数据库记录的孤儿文件。")
    print("此操作不可恢复。确认请输入 yes：", end="")
    if input().strip().lower() != "yes":
        print("已取消。")
        con.close()
        return 1

    for did, *_ in broken:
        cur.execute("DELETE FROM chat_messages WHERE detection_id=?", (did,))
        cur.execute("DELETE FROM detections WHERE id=?", (did,))
    con.commit()
    for p in orphans:
        p.unlink(missing_ok=True)
    print(f"\n已修复：删除失效记录 {len(broken)} 条、孤儿文件 {len(orphans)} 个。")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
