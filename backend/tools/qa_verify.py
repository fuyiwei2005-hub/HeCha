# -*- coding: utf-8 -*-
"""QA 独立验收脚本（严过关）。

原则：不复用工程师 tools/ 下的任何评测代码，A/B 两侧都自己重写一遍，
数字只认本脚本落盘的 _qa_result.json。

口径：逐字对齐 backend/tools/eval_top1.py 的 judge()。

用法：
    .\\.venv\\Scripts\\python.exe tools\\qa_verify.py
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings          # noqa: E402
from app.services import detector as D            # noqa: E402

ASSET = Path(r"D:\ai搭建\2026-10-06-16-15-16\_boxes2.json")
OUT = ROOT / "_qa_result.json"

# ── 几何判据：自己重写一遍，不从生产模块import，只用来做交叉校验──
def q_iou(a, b) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    sa = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    sb = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return inter / (sa + sb - inter + 1e-9)


def q_contain(a, b) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    sa = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    sb = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    small = min(sa, sb)
    return inter / small if small > 0 else 0.0


def q_area(a) -> float:
    return max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])


# ── 旧逻辑复刻（自己写，不抄 tools/ab_dedup.py）────────────────────
# 描述取自 docs/参赛材料/去重修复报告-空间聚类.md 第一节引用的旧代码：
#   1) 按 cls 分组，组内 NMS：IoU>=0.6 或 包含率>=0.35
#   2) 跨类别抑制：包含率>=0.7 且 中心距比<=0.25 且 置信度比>=1.3
#   3) 按类别聚合打分排序
OLD_IOU, OLD_CONTAIN = 0.6, 0.35
OLD_X_CONTAIN, OLD_X_CENTER, OLD_X_CONF = 0.7, 0.25, 1.3


def q_center_ratio(a, b) -> float:
    d = math.hypot((a[0] + a[2]) / 2 - (b[0] + b[2]) / 2,
                   (a[1] + a[3]) / 2 - (b[1] + b[3]) / 2)
    diag = min(math.hypot(a[2] - a[0], a[3] - a[1]),
               math.hypot(b[2] - b[0], b[3] - b[1]))
    return d / (diag + 1e-9)


def q_cluster_bonus(items, size) -> float:
    if len(items) < 2:
        return 0.0
    h, w = size
    diag = math.hypot(h, w)
    cs = [((b[2][0] + b[2][2]) / 2, (b[2][1] + b[2][3]) / 2) for b in items]
    near = sum(1 for i in range(len(cs)) for j in range(i + 1, len(cs))
               if math.dist(cs[i], cs[j]) < diag * 0.18)
    return near / (len(cs) * (len(cs) - 1) / 2)


def old_aggregate(raw, size, min_conf=0.30, bonus=0.6,
                  iou_t=OLD_IOU, con_t=OLD_CONTAIN, cross=True):
    keep = []
    for cls in {b[0] for b in raw}:
        grp = sorted([b for b in raw if b[0] == cls], key=lambda x: -x[1])
        kept = []
        for b in grp:
            if not any(q_iou(b[2], k[2]) >= iou_t or q_contain(b[2], k[2]) >= con_t
                       for k in kept):
                kept.append(b)
        keep.extend(kept)
    if cross:
        order = sorted(keep, key=lambda b: -b[1])
        victims = set()
        for i, hi in enumerate(order):
            if id(hi) in victims:
                continue
            for lo in order[i + 1:]:
                if id(lo) in victims or hi[0] == lo[0]:
                    continue
                if q_contain(hi[2], lo[2]) < OLD_X_CONTAIN:
                    continue
                if q_center_ratio(hi[2], lo[2]) > OLD_X_CENTER:
                    continue
                if hi[1] < lo[1] * OLD_X_CONF:
                    continue
                victims.add(id(lo))
        keep = [b for b in keep if id(b) not in victims]

    by = defaultdict(list)
    for b in keep:
        by[b[0]].append(b)
    scored = []
    for cls, items in by.items():
        best = max(x[1] for x in items)
        if best < min_conf:
            continue
        sc = sum(x[1] for x in items)
        if bonus:
            sc *= 1 + bonus * q_cluster_bonus(items, size)
        scored.append((sc, best, cls))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    out = []
    for _, _, cls in scored:
        out.extend(sorted(by[cls], key=lambda b: -b[1]))
    return out


# ── 判定口径：逐字对齐 eval_top1.py ──────────────────────────────
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


# ── 通用评测循环 ────────────────────────────────────────────────
def evaluate(boxes, cn, fn, dup_pred=None):
    """dup_pred(a,b)->bool 判定「输出里这两个框是同一只虫的重复」。
    不传则不统计重复框（避免自定义判据污染指标）。"""
    hit = any_hit = miss = wrong = 0
    total = 0
    ge3 = 0
    dup = 0
    dup_files = set()
    per = {}
    for name, rec in boxes.items():
        raw = [(int(c), float(cf), (float(a), float(b), float(x), float(y)))
               for c, cf, a, b, x, y, _s in rec["cands"]]
        ranked = fn(raw, tuple(rec["size"]))
        preds = to_preds(ranked, cn)
        truth = rec["truth"]
        top1, st = judge(preds, truth)
        nsp = len({p["class_cn"] for p in preds})
        per[name] = {"top1": top1, "status": st, "n": len(ranked), "species": nsp,
                     "preds": [{"cn": p["class_cn"], "conf": p["confidence"]}
                               for p in preds],
                     "boxes": [[round(v, 1) for v in b[2]] for b in ranked]}
        total += len(ranked)
        ge3 += nsp >= 3
        if dup_pred:
            for i in range(len(ranked)):
                for j in range(i + 1, len(ranked)):
                    if dup_pred(ranked[i][2], ranked[j][2]):
                        dup += 1
                        dup_files.add(name)
        hit += st == "命中"
        any_hit += st in ("命中", "任意命中")
        miss += st == "漏检"
        wrong += st == "误判"
    n = len(boxes)
    return {"top1": hit, "any": any_hit, "miss": miss, "wrong": wrong,
            "boxes": total, "per_img": round(total / n, 2), "ge3": ge3,
            "dup": dup, "dup_files": len(dup_files), "n": n, "per": per}


def summary(res):
    return {k: res[k] for k in
            ("top1", "any", "miss", "wrong", "boxes", "per_img", "ge3",
             "dup", "dup_files", "n")}


def main() -> int:
    s = get_settings()
    det = D.Detector()
    data = json.loads(ASSET.read_text(encoding="utf-8"))
    boxes, cn = data["boxes"], data["cn"]

    # 交叉校验：自写几何判据 vs 生产判据
    geo_xcheck = []
    for name, rec in boxes.items():
        raw = [(float(a), float(b), float(x), float(y))
               for _c, _cf, a, b, x, y, _s in rec["cands"]]
        for i in range(min(6, len(raw))):
            for j in range(i + 1, min(6, len(raw))):
                geo_xcheck.append(abs(q_iou(raw[i], raw[j]) - D._iou(raw[i], raw[j])))
                geo_xcheck.append(abs(q_contain(raw[i], raw[j]) - D._containment(raw[i], raw[j])))
    geo_max_err = max(geo_xcheck) if geo_xcheck else 0.0

    dup_pred = D._same_individual

    res = {
        "meta": {
            "asset": str(ASSET),
            "n_images": len(boxes),
            "n_cands": sum(len(v["cands"]) for v in boxes.values()),
            "detect_min_conf": s.detect_min_conf,
            "detect_cluster_bonus": s.detect_cluster_bonus,
            "MERGE_IOU": D.MERGE_IOU,
            "MERGE_CONTAIN": D.MERGE_CONTAIN,
            "MERGE_AREA_RATIO": D.MERGE_AREA_RATIO,
            "geo_crosscheck_max_err": geo_max_err,
        },
        "new_prod": summary(evaluate(boxes, cn, lambda r, z: det._aggregate(r, z),
                                     dup_pred)),
        "old_replica": summary(evaluate(boxes, cn, lambda r, z: old_aggregate(r, z),
                                        dup_pred)),
        # 历史对照：确认复刻能重现文档里的历史数字
        "old_replica_no_cross": summary(
            evaluate(boxes, cn, lambda r, z: old_aggregate(r, z, cross=False), dup_pred)),
        "old_replica_con070": summary(
            evaluate(boxes, cn,
                     lambda r, z: old_aggregate(r, z, iou_t=0.6, con_t=0.7), dup_pred)),
        "old_replica_con070_no_cross": summary(
            evaluate(boxes, cn,
                     lambda r, z: old_aggregate(r, z, iou_t=0.6, con_t=0.7, cross=False),
                     dup_pred)),
    }
    res["new_prod"]["per"] = None      # 明细单独存，减小体积
    res["old_replica"]["per"] = None

    # ── 任意命中掉点逐张归因 ─────────────────────────────────
    newres = evaluate(boxes, cn, lambda r, z: det._aggregate(r, z))
    oldres = evaluate(boxes, cn, lambda r, z: old_aggregate(r, z))
    dropped, gained = [], []
    for name, rec in boxes.items():
        t = rec["truth"]
        o, n = oldres["per"][name], newres["per"][name]
        o_has = o["status"] in ("命中", "任意命中")
        n_has = n["status"] in ("命中", "任意命中")
        if o_has and not n_has:
            dropped.append(name)
        if n_has and not o_has:
            gained.append(name)
    res["dropped"] = dropped
    res["gained"] = gained

    # ── 3x3 阈值敏感度（打生产模块常量，跑完复原）─────────────
    grid = []
    sv = (D.MERGE_IOU, D.MERGE_CONTAIN, D.MERGE_AREA_RATIO)
    try:
        for iou_t in (0.25, 0.30, 0.35):
            for con_t in (0.45, 0.50, 0.55):
                D.MERGE_IOU, D.MERGE_CONTAIN = iou_t, con_t
                r = evaluate(boxes, cn, lambda a, b: det._aggregate(a, b), dup_pred)
                grid.append({"iou": iou_t, "contain": con_t, **summary(r)})
    finally:
        D.MERGE_IOU, D.MERGE_CONTAIN, D.MERGE_AREA_RATIO = sv
    res["grid_3x3"] = grid

    # ── 面积护栏 A/B ──────────────────────────────────────────
    ab = []
    try:
        for ar in (1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 1e9):
            D.MERGE_AREA_RATIO = ar
            r = evaluate(boxes, cn, lambda a, b: det._aggregate(a, b), dup_pred)
            ab.append({"area_ratio": ("off" if ar > 1e8 else ar), **summary(r)})
    finally:
        D.MERGE_IOU, D.MERGE_CONTAIN, D.MERGE_AREA_RATIO = sv
    res["area_guard_ab"] = ab

    # ── 每图明细（新逻辑），供可视化与误并抽检使用 ──────────────
    detail = {}
    for name, rec in boxes.items():
        raw = [(int(c), float(cf), (float(a), float(b), float(x), float(y)))
               for c, cf, a, b, x, y, _s in rec["cands"]]
        ranked = det._aggregate(raw, tuple(rec["size"]))
        cl = D._cluster_individuals(raw)
        strong = [c for c in cl if max(b[1] for b in c) >= s.detect_min_conf]
        detail[name] = {
            "truth": rec["truth"], "size": rec["size"],
            "n_cands": len(raw), "n_clusters_raw": len(cl),
            "n_clusters_strong": len(strong), "n_out": len(ranked),
            "preds": [{"cn": cn[str(c)], "conf": round(cf, 4),
                       "box": [round(v, 1) for v in b]} for c, cf, b in ranked],
        }
    res["detail_new"] = detail
    detail_old = {}
    for name, rec in boxes.items():
        raw = [(int(c), float(cf), (float(a), float(b), float(x), float(y)))
               for c, cf, a, b, x, y, _s in rec["cands"]]
        ranked = old_aggregate(raw, tuple(rec["size"]))
        detail_old[name] = {"n_out": len(ranked),
                            "preds": [{"cn": cn[str(c)], "conf": round(cf, 4),
                                       "box": [round(v, 1) for v in b]}
                                      for c, cf, b in ranked]}
    res["detail_old_nbox"] = {k: v["n_out"] for k, v in detail_old.items()}
    res["detail_old"] = detail_old

    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())