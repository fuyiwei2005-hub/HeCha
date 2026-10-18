# -*- coding: utf-8 -*-
"""查残留的 18 对重叠输出框：是真的「一只虫两个框」，还是判据本该拦住的？

贪心聚类不做传递闭包，所以可能出现：A 被种子1 吸收、C 被种子2 吸收，
而 A 与 C 本身重叠 —— 两个代表框就都留下了。看看实际是哪些。
输出：_resid_out.txt
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.detector import (  # noqa: E402
    Detector, _area, _cluster_individuals, _containment, _iou, _same_individual,
)

ASSET = Path(r"D:\ai搭建\2026-10-06-16-15-16\_boxes2.json")
data = json.loads(ASSET.read_text(encoding="utf-8"))
boxes, cn = data["boxes"], data["cn"]
det = Detector()

L = ["残留重叠输出框对明细：",""]
n = 0
for name, rec in boxes.items():
    raw = [(int(c), float(cf), (float(a), float(b), float(x), float(y)))
           for c, cf, a, b, x, y, _s in rec["cands"]]
    out = det._aggregate(raw, tuple(rec["size"]))
    for i in range(len(out)):
        for j in range(i + 1, len(out)):
            a, b = out[i], out[j]
            iou, con = _iou(a[2], b[2]), _containment(a[2], b[2])
            if iou >= 0.30 or con >= 0.50:
                n += 1
                sa, sb = _area(a[2]), _area(b[2])
                ratio = max(sa, sb) / max(min(sa, sb), 1e-9)
                # 两框若直接互相比较，会被判为同一只吗？
                mutual = _same_individual(a[2], b[2])
                L.append(f"{name}  真值={rec['truth']}")
                L.append(f"   A cls{a[0]}={cn[str(a[0])]:<10}{a[1]:.4f} "
                         f"[{a[2][0]:.0f},{a[2][1]:.0f},{a[2][2]:.0f},{a[2][3]:.0f}] 面积{sa:.0f}")
                L.append(f"   B cls{b[0]}={cn[str(b[0])]:<10}{b[1]:.4f} "
                         f"[{b[2][0]:.0f},{b[2][1]:.0f},{b[2][2]:.0f},{b[2][3]:.0f}] 面积{sb:.0f}")
                L.append(f"   IoU={iou:.3f} 包含={con:.3f} 面积比={ratio:.2f} "
                         f"→ _same_individual(直接比较)={mutual}")
                L.append(f"   类别{'相同' if a[0] == b[0] else '不同'}")
                L.append("")
L.append(f"合计 {n} 对")

# 统计：这些代表框是否同簇来源
L.append("\n\n这些代表框各自属于哪个簇：")
for name, rec in boxes.items():
    raw = [(int(c), float(cf), (float(a), float(b), float(x), float(y)))
           for c, cf, a, b, x, y, _s in rec["cands"]]
    out = det._aggregate(raw, tuple(rec["size"]))
    bad = [(i, j) for i in range(len(out)) for j in range(i + 1, len(out))
           if _iou(out[i][2], out[j][2]) >= 0.30 or _containment(out[i][2], out[j][2]) >= 0.50]
    if not bad:
        continue
    cid = {}
    for k, c in enumerate(_cluster_individuals(raw)):
        for b in c:
            cid[id(b)] = k
    L.append(f"\n{name}  簇数={len(set(cid.values()))} 输出={len(out)}")
    for i, j in bad:
        L.append(f"   输出#{i}(簇{cid.get(id(out[i]))}) vs 输出#{j}(簇{cid.get(id(out[j]))})"
                 f"  簇号相同={cid.get(id(out[i])) == cid.get(id(out[j]))}")

Path(ROOT / "_resid_out.txt").write_text("\n".join(L), encoding="utf-8")
print("ok")