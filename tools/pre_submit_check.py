#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
参赛材料提交前总检查

对照官方要求逐项核对，输出一份可勾选的清单。
依据：_赛事官方文件/ 附件2 大赛方案，以及 参赛要求核对与补齐清单.md。

用法：
    python tools/pre_submit_check.py
退出码：0 = 无阻塞项；1 = 仍有阻塞项
"""

import json
import os
import re
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "docs", "参赛材料")
PDF = os.path.join(BASE, "PDF")
SHOTS = os.path.join(BASE, "截图")

results = []


def add(level, name, ok, detail=""):
    results.append((level, name, ok, detail))


def human(n):
    return f"{n/1024:.0f} KB"


# ---------- 1. 阻塞项：占位符 ----------
info_path = os.path.join(ROOT, "参赛信息.json")
ph_found = {}
for fn in ("软件设计文档.md", "AI使用声明.md", "作品简介.md"):
    p = os.path.join(BASE, fn)
    if os.path.exists(p):
        t = open(p, encoding="utf-8").read()
        for ph in dict.fromkeys(re.findall(r"\{\{([^}]+)\}\}", t)):
            ph_found.setdefault(ph, []).append(fn)

if ph_found:
    detail = "、".join(sorted(ph_found)) + "（填 参赛信息.json 后跑 tools/fill_placeholders.py --apply）"
    add("阻塞", "占位符已全部填充", False, detail)
else:
    add("阻塞", "占位符已全部填充", True, "")

# ---------- 2. 阻塞项：必交 PDF ----------
for name in ("软件设计文档", "作品简介", "AI使用声明"):
    p = os.path.join(PDF, name + ".pdf")
    if os.path.exists(p):
        add("阻塞", f"PDF 存在：{name}", True, human(os.path.getsize(p)))
    else:
        add("阻塞", f"PDF 存在：{name}", False, "缺失（缺设计文档 = 作品无效）")

# ---------- 3. 阻塞项：设计文档 PDF 页数 ----------
p = os.path.join(PDF, "软件设计文档.pdf")
if os.path.exists(p):
    try:
        import pypdf
        n = len(pypdf.PdfReader(p).pages)
        add("建议", "设计文档篇幅", n >= 15, f"{n} 页")
    except ImportError:
        add("建议", "设计文档篇幅", True, "（未装 pypdf，跳过）")

# ---------- 4. 阻塞项：3 幅核心功能截图 ----------
need_shots = [
    ("核心功能1_图片检测结果.png", "图片检测结果"),
    ("核心功能2_防治建议与引用溯源.png", "防治建议与引用溯源"),
    ("核心功能3_准确率实测数据.png", "准确率数据"),
]
for fn, label in need_shots:
    p = os.path.join(SHOTS, fn)
    if not os.path.exists(p):
        add("阻塞", f"核心截图：{label}", False, "缺失")
        continue
    sz = os.path.getsize(p)
    add("阻塞", f"核心截图：{label}", sz <= 1024 * 1024,
        f"{human(sz)}" + ("" if sz <= 1024 * 1024 else " ← 超过 1MB 上限"))

# ---------- 5. 阻塞项：源码 zip ----------
zipdir = os.path.join(ROOT, "参赛打包")
zips = [f for f in os.listdir(zipdir) if f.endswith(".zip")] if os.path.isdir(zipdir) else []
src_zip = None
for z in zips:
    if "源代码" in z:
        src_zip = os.path.join(zipdir, z)
        break
if src_zip:
    with zipfile.ZipFile(src_zip) as zf:
        names = zf.namelist()
    must = [
        "PestGuard/model_weights/best.pt",
        "PestGuard/backend/Dockerfile",
        "PestGuard/docker-compose.yml",
        "PestGuard/README.md",
    ]
    miss = [m for m in must if m not in names]
    venv = [n for n in names if "/.venv/" in n]
    add("阻塞", "源码 zip 完整", not miss and not venv,
        f"{os.path.basename(src_zip)} · {human(os.path.getsize(src_zip))}"
        + (f" · 缺 {miss}" if miss else "")
        + (f" · 残留 venv {len(venv)} 项" if venv else ""))
    # 禁商用图片不得外发
    nc_imgs = [n for n in names if any(x in n for x in ("_外部验证集", "_队友交图_待检"))]
    add("阻塞", "源码 zip 不含禁商用图集", not nc_imgs,
        "已排除" if not nc_imgs else f"⚠ 仍含 {len(nc_imgs)} 张 NC 授权图片")
else:
    add("阻塞", "源码 zip 完整", False, "未找到 zip，跑 tools/build_source_zip.py")

# ---------- 6. 建议项：测试账号 ----------
if os.path.exists(os.path.join(BASE, "软件设计文档.md")):
    t = open(os.path.join(BASE, "软件设计文档.md"), encoding="utf-8").read()
    has = "测试账号" in t and "测试用户名" in t
    add("阻塞", "设计文档含测试账号（官方要求显著位置）", has, "")

# ---------- 7. 建议项：官方检查点覆盖 ----------
doc_path = os.path.join(BASE, "软件设计文档.md")
if os.path.exists(doc_path):
    t = open(doc_path, encoding="utf-8").read()
    points = {
        "软硬件平台及版本号": ["Python 3.12", "Windows 11", "CPU"],
        "开发工具与语言版本": ["FastAPI", "版本"],
        "大模型名称及版本": ["DeepSeek"],
        "AI 代码占比": ["AI代码占比", "AI 编写代码比例"],
        "第三方开源代码标注": ["开源", "Ultralytics"],
        "需求分析": ["需求分析"],
        "设计思路": ["概要设计"],
        "功能模块": ["模块划分"],
        "操作步骤说明": ["三分钟演示", "操作步骤"],
    }
    for label, kws in points.items():
        hit = any(k in t for k in kws)
        add("建议", f"覆盖检查点：{label}", hit, "")

# ---------- 8. 阻塞项：公网可访问（官方红线） ----------
# 不再是写死的 False：从参赛信息.json 读地址，并真的发一次 HTTP 请求确认能通。
deploy_url = ""
info_path = os.path.join(ROOT, "参赛信息.json")
if os.path.exists(info_path):
    try:
        with open(info_path, encoding="utf-8") as f:
            cfg = json.load(f)
        deploy_url = str(cfg.get("公网地址", "")).strip()
    except Exception:  # noqa: BLE001
        deploy_url = ""

deploy_ok = False
deploy_note = "参赛信息.json 里还没有填公网地址"
if deploy_url and not deploy_url.startswith("{{"):
    try:
        req = urllib.request.Request(
            deploy_url.rstrip("/") + "/api/health", method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", "replace")
            deploy_ok = resp.status == 200 and '"status"' in body
            deploy_note = f"{deploy_url} -> HTTP {resp.status}"
            # health 里 redis/schema 有异常也要提醒，别只看 200
            for bad in ("redis\": \"error", "schema\": \"mismatch"):
                if bad in body:
                    deploy_note += f"（注意：health 中 {bad.split(chr(34))[0]} 非正常）"
    except Exception as exc:  # noqa: BLE001
        deploy_note = f"{deploy_url} 访问失败：{exc.__class__.__name__}"
else:
    pass

add("阻塞", "公网可访问（官方红线）", deploy_ok, deploy_note)

# ---------- 输出 ----------
print("=" * 68)
print("PestGuard 参赛材料提交前检查")
print("=" * 68)
blocking = [r for r in results if r[0] == "阻塞"]
advise = [r for r in results if r[0] == "建议"]

for level, items in (("阻塞项", blocking), ("建议项", advise)):
    if not items:
        continue
    print(f"\n【{level}】")
    for _, name, ok, detail in items:
        mark = "OK  " if ok else "TODO"
        line = f"  {mark}  {name}"
        if detail:
            line += f"   —— {detail}"
        print(line)

n_todo = sum(1 for r in blocking if not r[2])
print("\n" + "=" * 68)
if n_todo:
    print(f"结论：仍有 {n_todo} 个阻塞项未完成，暂不具备提交条件。")
else:
    print("结论：所有阻塞项已通过，可以提交。")
print("=" * 68)
sys.exit(1 if n_todo else 0)
