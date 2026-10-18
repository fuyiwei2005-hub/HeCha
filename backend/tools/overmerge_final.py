# -*- coding: utf-8 -*-
"""核对报告第三节/第七节引用的「误并框对」数字（330 / 93 / 71）。

这几个数来自不同口径，必须重新用统一脚本算一遍，不能各写各的。
统一口径：181 张图里「同图内彼此几乎不重叠、必然是不同个体」的高分框对
（IoU < 0.2917 且包含率 < 0.4981），被聚进同一个簇的对数。
输出：_overmerge_final.txt
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.detector import _containment, _iou  # noqa: E402

ASSET = Path(r"D:\ai搭建\2026-10-06-16-15-16\_boxes2.json")
data = json.loads(ASSET.read_text(encoding="utf-8"))
boxes, cn = data["boxes"], data["cn"]

REAL_IOU_CEIL, REAL_CON_CEIL = 0.2917, 0.4981
L = ["统一口径的「误并框对」统计", ""]


def clusters_closure(raw, iou_t, con_t):
    n = len(raw)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if _iou(raw[i][2], raw[j][2]) >= iou_t or \
                    _containment(raw[i][2], raw[j][2]) >= con_t:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri
    g = defaultdict(list)
    for i in range(n):
        g[find(i)].append(raw[i])
    return list(g.values())


def clusters_seeded(raw, iou_t, con_t):
    order = sorted(range(len(raw)), key=lambda i: -raw[i][1])
    used = [False] * len(raw)
    out = []
    for i in order:
        if used[i]:
            continue
        used[i] = True
        cl = [raw[i]]
        for j in order:
            if used[j]:
                continue
            if _iou(raw[i][2], raw[j][2]) >= iou_t or \
                    _containment(raw[i][2], raw[j][2]) >= con_t:
                used[j] = True
                cl.append(raw[j])
        out.append(cl)
    return out


def count(fn, iou_t, con_t):
    pairs = 0
    files = set()
    for name, rec in boxes.items():
        raw = [(int(c), float(cf), (float(a), float(b), float(x), float(y)))
               for c, cf, a, b, x, y, _s in rec["cands"]]
        strong = [b for b in raw if b[1] >= 0.30]
        if len(strong) < 2:
            continue
        cid = {}
        for i, c in enumerate(fn(raw, iou_t, con_t)):
            for b in c:
                cid[id(b)] = i
        for a_ in range(len(strong)):
            for b_ in range(a_ + 1, len(strong)):
                x, y = strong[a_], strong[b_]
                if _iou(x[2], y[2]) < REAL_IOU_CEIL and \
                        _containment(x[2], y[2]) < REAL_CON_CEIL:
                    if cid.get(id(x)) is not None and cid.get(id(x)) == cid.get(id(y)):
                        pairs += 1
                        files.add(name)
    return pairs, len(files)


for label, fn, i, c in (
    ("传递闭包（并查集）", clusters_closure, 0.30, 0.50),
    ("贪心种子 · 无面积护栏", clusters_seeded, 0.30, 0.50),
):
    p, f = count(fn, i, c)
    L.append(f"{label:<24} iou={i} con={c} → 误并 {p} 对，涉及 {f} 张图")

# 生产用的判据（含面积护栏）—— 签名不同，单独包一层
from app.services.detector import _cluster_individuals  # noqa: E402


def _prod(raw, iou_t, con_t):
    return _cluster_individuals(raw)


p, f = count(_prod, 0.30, 0.50)
L.append(f"{'生产值（含面积护栏）':<24} iou=0.30 con=0.50 → 误并 {p} 对，涉及 {f} 张图")

Path(ROOT / "_overmerge_final.txt").write_text("\n".join(L), encoding="utf-8")
print("ok")