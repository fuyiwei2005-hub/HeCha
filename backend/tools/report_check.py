# -*- coding: utf-8 -*-
"""核对报告里引用的几处数字，避免材料里出现不实数据。

1. 簇大小分布（报告第一节表格）
2. 单图候选框数量范围（风险表里写的「2~45 个，最多 2025 次比较」）
3. 黑点蚧_04 旧24 → 新 10
4. 吸事件 37 次
5. 测试数量
输出：_report_check.txt
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.detector import (  # noqa: E402
    Detector, MERGE_AREA_RATIO, _area, _cluster_individuals,
)

ASSET = Path(r"D:\ai搭建\2026-10-06-16-15-16\_boxes2.json")
data = json.loads(ASSET.read_text(encoding="utf-8"))
boxes, cn = data["boxes"], data["cn"]
det = Detector()
L = []

sizes = []
cand_counts = []
magnet = 0
for name, rec in boxes.items():
    raw = [(int(c), float(cf), (float(a), float(b), float(x), float(y)))
           for c, cf, a, b, x, y, _s in rec["cands"]]
    cand_counts.append(len(raw))
    cl = _cluster_individuals(raw)
    for c in cl:
        sizes.append(len(c))
        if len(c) >= 2:
            seed = max(c, key=lambda b: b[1])
            sa = _area(seed[2])
            for b in c:
                if b is seed:
                    continue
                if sa > 4 * max(_area(b[2]), 1e-9):
                    magnet += 1

cnt = Counter(sizes)
mx = max(sizes)
L.append("簇大小分布（完整，含 >=11）：")
for k in range(1, mx + 1):
    L.append(f"  {k:>2} 个框 → {cnt.get(k, 0)} 簇")
L.append(f"  簇总数 = {len(sizes)}；1 框簇占比 = {cnt.get(1, 0) / len(sizes) * 100:.1f}%")

L.append("")
L.append(f"单图候选框数：min={min(cand_counts)} max={max(cand_counts)} "
         f"→ O(n^2) 最大 {max(cand_counts) ** 2} 次框比较")
L.append(f"  报告里写的「2~45 个」→ 实际应为 {min(cand_counts)}~{max(cand_counts)}")

L.append("")
rec = boxes["黑点蚧_04.jpg"]
raw = [(int(c), float(cf), (float(a), float(b), float(x), float(y)))
       for c, cf, a, b, x, y, _s in rec["cands"]]
new = det._aggregate(raw, tuple(rec["size"]))
L.append(f"黑点蚧_04.jpg：候选 {len(raw)} 个 → 新逻辑输出 {len(new)} 框"
         f"（簇数 {len(_cluster_individuals(raw))}）")

L.append("")
L.append(f"磁吸事件（种子面积 > 4x 被吸收框）= {magnet} 次，报告写37")
L.append(f"MERGE_AREA_RATIO = {MERGE_AREA_RATIO}")

Path(ROOT / "_report_check.txt").write_text("\n".join(L), encoding="utf-8")
print("ok")