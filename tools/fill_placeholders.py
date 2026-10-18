#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
参赛材料占位符一键填充

背景：材料里有 10 个占位符变量，散落在 4 个 md 文件中手工替换极易漏改。
本脚本读 `参赛信息.json`，批量替换后重新导出 PDF。

用法：
    1) 复制 参赛信息.example.json → 参赛信息.json，按注释填好
    2) python tools/fill_placeholders.py --check     # 只检查缺哪些
    3) python tools/fill_placeholders.py --apply     # 填充并重出 PDF
"""

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "docs", "参赛材料")
INFO = os.path.join(ROOT, "参赛信息.json")

# 必须填的字段（官方硬性要求）
REQUIRED = [
    "团队名称",
    "成员1", "成员2", "成员3",
    "分工1", "分工2", "分工3",
    "指导教师",
    "公网地址",
    "测试用户名", "测试密码",
    "AI代码占比",
]

# 需要填充占位符的文件
TARGET_MD = [
    "软件设计文档.md",
    "AI使用声明.md",
    "作品简介.md",
]


def load_info() -> dict:
    if not os.path.exists(INFO):
        print(f"找不到配置文件：{INFO}")
        print("请先复制 参赛信息.example.json 为 参赛信息.json 并填写")
        sys.exit(1)
    with open(INFO, encoding="utf-8") as f:
        return json.load(f)


# 示例文件里的占位文案，不算已填
_PLACEHOLDER_VALUES = {
    "填", "姓名", "指导教师姓名", "如：", "填演示账号", "填百分比",
    "填队伍名称", "https://请填写", "填一个", "指导教师",
}


def _is_filled(ph: str, info: dict) -> bool:
    """判断某占位符是否已真实填写。未填、仍是模板占位、仍是示例文案都算未填。"""
    val = info.get(ph, "")
    if not val or not isinstance(val, str):
        return False
    v = val.strip()
    if not v or v.startswith("{{"):
        return False
    # 形如 "填XXX" / "姓名1" / "如：XXX" / "https://请填写" 都视为未填
    for token in _PLACEHOLDER_VALUES:
        if v.startswith(token) or token in v:
            return False
    return True


def scan_placeholders():
    found = {}
    for fn in TARGET_MD:
        p = os.path.join(BASE, fn)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            t = f.read()
        for ph in dict.fromkeys(re.findall(r"\{\{([^}]+)\}\}", t)):
            found.setdefault(ph, []).append(fn)
    return found


def cmd_check(_args) -> int:
    info = load_info()
    found = scan_placeholders()

    print("=" * 60)
    print("占位符检查")
    print("=" * 60)
    missing = []
    for ph, files in sorted(found.items()):
        ok = _is_filled(ph, info)
        mark = "OK  " if ok else "MISS"
        if not ok:
            missing.append(ph)
        cur = info.get(ph, "")
        show = cur if ok else (cur if cur else "（空）")
        print(f"  {mark}  {ph:<12} 当前值: {show}")

    if not missing:
        print("\n全部已填写，可以执行 --apply")
        return 0

    print(f"\n仍缺 {len(missing)} 项：{', '.join(missing)}")
    print(f"请编辑 {INFO}")
    return 1


def cmd_apply(args) -> int:
    info = load_info()
    found = scan_placeholders()

    missing = [ph for ph in found if not _is_filled(ph, info)]
    if missing:
        print(f"仍有 {len(missing)} 项未填写，拒绝执行：{', '.join(missing)}")
        print("先跑 --check 查看清单")
        return 1

    # 备份
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    backup = os.path.join(ROOT, "参赛打包", f"材料备份_{stamp}")
    os.makedirs(backup, exist_ok=True)
    for fn in TARGET_MD:
        src = os.path.join(BASE, fn)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(backup, fn))
    print(f"已备份到 {backup}")

    total = 0
    for fn in TARGET_MD:
        p = os.path.join(BASE, fn)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            t = f.read()
        before = t
        for ph in found:
            t = t.replace("{{" + ph + "}}", str(info[ph]))
        if t != before:
            with open(p, "w", encoding="utf-8") as f:
                f.write(t)
            n = len(re.findall(r"\{\{[^}]+\}\}", t))
            total += 1
            print(f"  已填充 {fn}" + (f"（剩余 {n} 处未识别占位符）" if n else ""))
            if n:
                for ph in dict.fromkeys(re.findall(r"\{\{([^}]+)\}\}", t)):
                    print(f"      ⚠ 未在配置中找到: {ph}")

    print(f"\n共处理 {total} 个文件")

    # 重出 PDF
    if not args.no_pdf:
        print("\n重新导出 PDF ...")
        py = os.path.join(ROOT, "backend", ".venv", "Scripts", "python.exe")
        script = os.path.join(ROOT, "tools", "md2pdf.py")
        if os.path.exists(py):
            import subprocess
            r = subprocess.run([py, script, "--all"], capture_output=True, text=True)
            print(r.stdout)
            if r.returncode != 0:
                print("PDF 导出失败：", r.stderr)
                return 1
        else:
            print("找不到 venv python，跳过 PDF 导出")

    # 作品简介单独处理（它结构不同，单独转）
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="只检查，不修改")
    g.add_argument("--apply", action="store_true", help="填充并重出 PDF")
    ap.add_argument("--no-pdf", action="store_true", help="跳过 PDF 导出")
    args = ap.parse_args()
    return cmd_check(args) if args.check else cmd_apply(args)


if __name__ == "__main__":
    sys.exit(main())
