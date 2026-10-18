# -*- coding: utf-8 -*-
"""补测报告需要的两组数字：
  A) 关掉面积护栏时的簇大小分布与磁吸次数（用来论证护栏的价值）
  B) 开护栏（生产值）时的簇大小分布（报告正文要用这个）
输出：_report_check2.txt
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.detector import _area, _cluster_individuals, _containment, _iou  # noqa: E402

ASSET = Path(r"D:\ai搭建\2026-10-06-16-15-16\_boxes2.json")
data = json.loads(ASSET.read_text(encoding="utf-8"))
boxes = data["boxes"]
L = []


def clusters_no_guard(raw, iou_t=0.30, con_t=0.50):
    order = sorted(range(len(raw)), key=lambda i: -raw[i][1])
    taken = [False] * len(raw)
    out = []
    for i in order:
        if taken[i]:
            continue
        taken[i] = True
        cl = [raw[i]]
        for j in order:
            if taken[j]:
                continue
            if _iou(raw[i][2], raw[j][2]) >= iou_t or \
                    _containment(raw[i][2], raw[j][2]) >= con_t:
                taken[j] = True
                cl.append(raw[j])
        out.append(cl)
    return out


for label, fn in (("生产值（含面积护栏4.0）", _cluster_individuals),
                  ("关掉面积护栏", clusters_no_guard)):
    sizes = []
    magnet = 0
    ncand = []
    for name, rec in boxes.items():
        raw = [(int(c), float(cf), (float(a), float(b), float(x), float(y)))
               for c, cf, a, b, x, y, _s in rec["cands"]]
        ncand.append(len(raw))
        for c in fn(raw):
            sizes.append(len(c))
            if len(c) >= 2:
                seed = max(c, key=lambda b: b[1])
                sa = _area(seed[2])
                for b in c:
                    if b is not seed and sa > 4 * max(_area(b[2]), 1e-9):
                        magnet += 1
    cnt = Counter(sizes)
    L.append(f"【{label}】")
    L.append(f"  簇总数 = {len(sizes)}")
    row = " ".join(f"{k}→{cnt.get(k, 0)}" for k in range(1, max(sizes) + 1))
    L.append(f"  分布：{row}")
    L.append(f"  1 框簇 = {cnt.get(1, 0)} ({cnt.get(1, 0) / len(sizes) * 100:.1f}%)，"
             f"≥2 框簇 = {len(sizes) - cnt.get(1, 0)} "
             f"({(len(sizes) - cnt.get(1, 0)) / len(sizes) * 100:.1f}%)")
    L.append(f"  磁吸事件（种子面积 > 4x）= {magnet}")
    L.append(f"  单图候选框数 min={min(ncand)} max={max(ncand)}，"
             f"有 0 候选的图 = {sum(1 for x in ncand if x == 0)} 张")
    L.append("")

Path(ROOT / "_report_check2.txt").write_text("\n".join(L), encoding="utf-8")
print("ok")