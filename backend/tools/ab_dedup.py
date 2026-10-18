# -*- coding: utf-8 -*-
"""离线 A/B：把 _boxes2.json 的候选框喂给新旧两套聚合逻辑，用 eval_top1.judge 口径评测。

生产代码不参与拟合 —— 这里只是把 detector._aggregate 的两版实现各抄一份，
用来在不重跑推理的前提下网格搜索阈值。选定阈值后再手工搬进 detector.py。

用法：
    .\\.venv\\Scripts\\python.exe tools\\ab_dedup.py            # 网格搜索
    .\\.venv\\Scripts\\python.exe tools\\ab_dedup.py --detail   # 附带逐图明细
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.detector import _containment, _iou  # noqa: E402  几何判据共用生产实现

ASSET = Path(r"D:\ai搭建\2026-10-06-16-15-16\_boxes2.json")

# 与 app/core/config.py 的默认值保持一致（.env 未覆盖这两项）
DETECT_MIN_CONF = 0.30
CLUSTER_BONUS = 0.6


# ── 旧逻辑（当前生产代码的逐行复刻，用作 A/B 的对照组）────────────────
MERGE_IOU_OLD = 0.6
MERGE_CONTAIN_OLD = 0.35
CROSS_CONTAIN = 0.7
CROSS_CENTER = 0.25
CROSS_CONF_RATIO = 1.3


def _center_ratio(a, b) -> float:
    import math
    d = math.hypot((a[0] + a[2]) / 2 - (b[0] + b[2]) / 2,
                   (a[1] + a[3]) / 2 - (b[1] + b[3]) / 2)
    diag = min(math.hypot(a[2] - a[0], a[3] - a[1]),
               math.hypot(b[2] - b[0], b[3] - b[1]))
    return d / (diag + 1e-9)


def _suppress_cross_class_old(boxes):
    order = sorted(boxes, key=lambda b: -b[1])
    victims = set()
    for i, hi in enumerate(order):
        if id(hi) in victims:
            continue
        for lo in order[i + 1:]:
            if id(lo) in victims or hi[0] == lo[0]:
                continue
            if _containment(hi[2], lo[2]) < CROSS_CONTAIN:
                continue
            if _center_ratio(hi[2], lo[2]) > CROSS_CENTER:
                continue
            if hi[1] < lo[1] * CROSS_CONF_RATIO:
                continue
            victims.add(id(lo))
    return [b for b in boxes if id(b) not in victims]


def _cluster_bonus(items, size) -> float:
    import math
    if len(items) < 2:
        return 0.0
    h, w = size
    diag = math.hypot(h, w)
    centers = [((b[2][0] + b[2][2]) / 2, (b[2][1] + b[2][3]) / 2) for b in items]
    near = sum(1 for i in range(len(centers)) for j in range(i + 1, len(centers))
               if math.dist(centers[i], centers[j]) < diag * 0.18)
    pairs = len(centers) * (len(centers) - 1) / 2
    return near / pairs


def _aggregate_old(raw, size):
    keep = []
    for cls in {b[0] for b in raw}:
        group = sorted([b for b in raw if b[0] == cls], key=lambda x: -x[1])
        kept = []
        for b in group:
            if not any(_iou(b[2], k[2]) >= MERGE_IOU_OLD
                       or _containment(b[2], k[2]) >= MERGE_CONTAIN_OLD for k in kept):
                kept.append(b)
        keep.extend(kept)
    keep = _suppress_cross_class_old(keep)

    by_cls = defaultdict(list)
    for b in keep:
        by_cls[b[0]].append(b)
    scored = []
    for cls, items in by_cls.items():
        best = max(b[1] for b in items)
        if best < DETECT_MIN_CONF:
            continue
        score = sum(b[1] for b in items)
        if CLUSTER_BONUS:
            score *= 1 + CLUSTER_BONUS * _cluster_bonus(items, size)
        scored.append((score, best, cls))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    out = []
    for _, _, cls in scored:
        out.extend(sorted(by_cls[cls], key=lambda b: -b[1]))
    return out


# ── 新逻辑：空间聚类 → 簇内类别投票 → 置信度过滤 → 原有打分排序 ────────
def _spatial_clusters(raw, iou_thr, contain_thr):
    """并查集：IoU 或包含率达标即视为同一个体，传递闭包。

    返回 list[list[tuple]]，每个子列表是该簇的原始候选框。
    """
    n = len(raw)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    for i in range(n):
        for j in range(i + 1, n):
            if _iou(raw[i][2], raw[j][2]) >= iou_thr or \
                    _containment(raw[i][2], raw[j][2]) >= contain_thr:
                union(i, j)

    groups: dict[int, list[tuple]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(raw[i])
    return list(groups.values())


def _aggregate_new(raw, size, iou_thr, contain_thr, min_conf=DETECT_MIN_CONF):
    keep = []
    for cluster in _spatial_clusters(raw, iou_thr, contain_thr):
        rep = max(cluster, key=lambda b: b[1])   # 代表框 = 簇内最高置信度
        if rep[1] < min_conf:
            continue
        keep.append(rep)

    by_cls = defaultdict(list)
    for b in keep:
        by_cls[b[0]].append(b)
    scored = []
    for cls, items in by_cls.items():
        best = max(b[1] for b in items)
        if best < min_conf:
            continue
        score = sum(b[1] for b in items)
        if CLUSTER_BONUS:
            score *= 1 + CLUSTER_BONUS * _cluster_bonus(items, size)
        scored.append((score, best, cls))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    out = []
    for _, _, cls in scored:
        out.extend(sorted(by_cls[cls], key=lambda b: -b[1]))
    return out


# ── 评测（口径对齐 tools/eval_top1.py 的 judge）─────────────────────────
def judge(plist, truth):
    if not plist:
        return "", "漏检"
    top = max(plist, key=lambda x: x["confidence"])
    name = top.get("class_cn") or top.get("class")
    if name == truth:
        return name, "命中"
    if any((x.get("class_cn") or x.get("class")) == truth for x in plist):
        return name, "任意命中"
    return name, "误判"


def to_preds(ranked, cn):
    return [{"class": str(c), "class_cn": cn[str(c)], "confidence": round(conf, 4)}
            for c, conf, _ in ranked]


def evaluate(boxes, cn, fn):
    hit = any_hit = miss = wrong = 0
    total_boxes = 0
    species_per_img = []
    multi_box_same_cls = 0
    ge3_species = 0
    per_file = {}
    for name, rec in boxes.items():
        size = tuple(rec["size"])
        raw = [(int(c), float(cf), (float(x1), float(y1), float(x2), float(y2)))
               for c, cf, x1, y1, x2, y2, _src in rec["cands"]]
        ranked = fn(raw, size)
        preds = to_preds(ranked, cn)
        truth = rec["truth"]
        top1, status = judge(preds, truth)
        per_file[name] = (top1, status, len(ranked),
                          len({p["class_cn"] for p in preds}))
        total_boxes += len(ranked)
        ns = len({p["class_cn"] for p in preds})
        species_per_img.append(ns)
        if any(v == 2 for v in
               [sum(1 for p in preds if p["class_cn"] == c)
                for c in {p["class_cn"] for p in preds}]):
            multi_box_same_cls += 1
        if ns >= 3:
            ge3_species += 1
        if status == "命中":
            hit += 1
        if status in ("命中", "任意命中"):
            any_hit += 1
        elif status == "漏检":
            miss += 1
        else:
            wrong += 1
    n = len(boxes)
    return {
        "top1": hit, "any": any_hit, "miss": miss, "wrong": wrong,
        "boxes": total_boxes,
        "per_img": round(total_boxes / n, 2),
        "multi_box_cls": multi_box_same_cls, "ge3": ge3_species,
        "per_file": per_file,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detail", action="store_true")
    args = ap.parse_args()

    data = json.loads(ASSET.read_text(encoding="utf-8"))
    boxes, cn = data["boxes"], data["cn"]

    lines: list[str] = []
    lines.append(f"图集 {len(boxes)} 张，候选框 {sum(len(v['cands']) for v in boxes.values())} 个\n")

    base = evaluate(boxes, cn, _aggregate_old)
    lines.append("【基线 · 旧逻辑（类内 NMS + 跨类别抑制）】")
    lines.append(f"  Top-1 {base['top1']}/{len(boxes)} = {base['top1']/len(boxes)*100:.1f}%")
    lines.append(f"  任意命中 {base['any']}/{len(boxes)} = {base['any']/len(boxes)*100:.1f}%")
    lines.append(f"  漏检 {base['miss']} · 误判 {base['wrong']}")
    lines.append(f"  总检出框 {base['boxes']} · 平均 {base['per_img']} 框/图")
    lines.append(f"  同类别多框的图 {base['multi_box_cls']} · ≥3虫种的图 {base['ge3']}\n")

    tgt = "稻纵卷叶螟_04.jpg"
    lines.append(f"目标图 {tgt}：旧逻辑 = {base['per_file'].get(tgt)}\n")

    lines.append("【新逻辑 · 空间聚类网格搜索】")
    lines.append("  iou\\contain  top1  任意命中 漏检  总框  框/图 同类多框 ≥3虫种  目标图框数")
    results = {}
    grid = []
    for iou_thr in (0.20, 0.25, 0.30, 0.35, 0.40):
        for contain_thr in (0.40, 0.45, 0.50, 0.55, 0.60, 0.65):
            r = evaluate(boxes, cn,
                         lambda raw, size, i=iou_thr, c=contain_thr:
                         _aggregate_new(raw, size, i, c))
            grid.append((iou_thr, contain_thr, r))
            results[(iou_thr, contain_thr)] = r
            tf = r["per_file"].get(tgt, ("", "", 0, 0))[2]
            lines.append(f"  {iou_thr:.2f} \\ {contain_thr:.2f}   "
                         f"{r['top1']:>4}  {r['any']:>6}  {r['miss']:>4}  "
                         f"{r['boxes']:>5}  {r['per_img']:>5}  {r['multi_box_cls']:>6}  "
                         f"{r['ge3']:>5}  {tf:>8}")

    # 在「Top-1 与任意命中都不低于基线」的组合里，挑总框最少者
    ok = [(i, c, r) for i, c, r in grid
          if r["top1"] >= base["top1"] and r["any"] >= base["any"]]
    lines.append("")
    if ok:
        best = min(ok, key=lambda t: (t[2]["boxes"], -t[0], -t[1]))
        i, c, r = best
        lines.append(f"★ 不掉点前提下的最省框组合：iou={i:.2f} contain={c:.2f}")
        lines.append(f"  Top-1 {r['top1']} · 任意命中 {r['any']} · 漏检 {r['miss']} · "
                     f"总框 {r['boxes']} · 框/图 {r['per_img']} · ≥3虫种 {r['ge3']}")
        lines.append(f"  目标图 {tgt} 框数 = {r['per_file'][tgt][2]}")
        ok2 = sorted(ok, key=lambda t: t[2]["boxes"])
        lines.append("  （同条件下按总框升序前 8 名）")
        for i2, c2, r2 in ok2[:8]:
            lines.append(f"    iou={i2:.2f} contain={c2:.2f} → 框 {r2['boxes']} "
                         f"top1 {r2['top1']} any {r2['any']} miss {r2['miss']} "
                         f"≥3虫种 {r2['ge3']} 目标图 {r2['per_file'][tgt][2]}")

    Path(ROOT / "_ab_out.txt").write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())