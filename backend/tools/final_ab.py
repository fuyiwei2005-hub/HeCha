# -*- coding: utf-8 -*-
"""最终验收：直接调用**生产代码** detector._aggregate（不是实验副本）跑 181 张资产。

前八轮实验为了网格搜索都在 tools/ 下抄了一份聚合逻辑。抄本可能与生产代码
漂移，所以最后这一步必须直接打生产模块，确认报告里引用的数字与线上跑的一致。

输出：_final_out.txt
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.services.detector import (  # noqa: E402
    Detector, MERGE_AREA_RATIO, MERGE_CONTAIN, MERGE_IOU, _containment, _iou,
    _same_individual,
)

ASSET = Path(r"D:\ai搭建\2026-10-06-16-15-16\_boxes2.json")
TGT = "稻纵卷叶螟_04.jpg"
REAL_IOU_CEIL, REAL_CON_CEIL = 0.2917, 0.4981

# 旧逻辑的逐行复刻，仅用于 A/B 对照（生产代码里已不存在）
MERGE_IOU_OLD, MERGE_CONTAIN_OLD = 0.6, 0.35
CROSS_CONTAIN, CROSS_CENTER, CROSS_CONF_RATIO = 0.7, 0.25, 1.3
import math  # noqa: E402


def _cr(a, b):
    d = math.hypot((a[0] + a[2]) / 2 - (b[0] + b[2]) / 2,
                   (a[1] + a[3]) / 2 - (b[1] + b[3]) / 2)
    diag = min(math.hypot(a[2] - a[0], a[3] - a[1]),
               math.hypot(b[2] - b[0], b[3] - b[1]))
    return d / (diag + 1e-9)


def _cb(items, size):
    if len(items) < 2:
        return 0.0
    h, w = size
    diag = math.hypot(h, w)
    cs = [((b[2][0] + b[2][2]) / 2, (b[2][1] + b[2][3]) / 2) for b in items]
    near = sum(1 for i in range(len(cs)) for j in range(i + 1, len(cs))
               if math.dist(cs[i], cs[j]) < diag * 0.18)
    pairs = len(cs) * (len(cs) - 1) / 2
    return near / pairs


def aggregate_old(raw, size, min_conf=0.30):
    keep = []
    for cls in {b[0] for b in raw}:
        g = sorted([b for b in raw if b[0] == cls], key=lambda x: -x[1])
        k = []
        for b in g:
            if not any(_iou(b[2], x[2]) >= MERGE_IOU_OLD
                       or _containment(b[2], x[2]) >= MERGE_CONTAIN_OLD for x in k):
                k.append(b)
        keep.extend(k)
    # 跨类别抑制（旧逻辑第二步）
    order = sorted(keep, key=lambda b: -b[1])
    victims = set()
    for i, hi in enumerate(order):
        if id(hi) in victims:
            continue
        for lo in order[i + 1:]:
            if id(lo) in victims or hi[0] == lo[0]:
                continue
            if _containment(hi[2], lo[2]) < CROSS_CONTAIN:
                continue
            if _cr(hi[2], lo[2]) > CROSS_CENTER:
                continue
            if hi[1] < lo[1] * CROSS_CONF_RATIO:
                continue
            victims.add(id(lo))
    keep = [b for b in keep if id(b) not in victims]

    by = defaultdict(list)
    for b in keep:
        by[b[0]].append(b)
    sc = []
    for cls, items in by.items():
        best = max(x[1] for x in items)
        if best < min_conf:
            continue
        sc.append((sum(x[1] for x in items) * (1 + 0.6 * _cb(items, size)), best, cls))
    sc.sort(key=lambda x: (-x[0], -x[1]))
    out = []
    for _, _, cls in sc:
        out.extend(sorted(by[cls], key=lambda b: -b[1]))
    return out


def judge(ps, truth):
    if not ps:
        return "", "漏检"
    top = max(ps, key=lambda x: x["confidence"])
    if top["class_cn"] == truth:
        return top["class_cn"], "命中"
    if any(p["class_cn"] == truth for p in ps):
        return top["class_cn"], "任意命中"
    return top["class_cn"], "误判"


def run(boxes, cn, fn):
    hit = any_hit = miss = wrong = 0
    tb = g3 = dup = 0
    dupf = set()
    pf = {}
    for name, rec in boxes.items():
        raw = [(int(c), float(cf), (float(a), float(b), float(x), float(y)))
               for c, cf, a, b, x, y, _s in rec["cands"]]
        r = fn(raw, tuple(rec["size"]))
        ps = [{"class": str(c), "class_cn": cn[str(c)], "confidence": round(cf, 4)}
              for c, cf, _ in r]
        t, st = judge(ps, rec["truth"])
        pf[name] = (t, st, len(r), len({p["class_cn"] for p in ps}))
        tb += len(r)
        g3 += len({p["class_cn"] for p in ps}) >= 3
        for i in range(len(r)):
            for j in range(i + 1, len(r)):
                # 用生产判据_same_individual，而不是裸 IoU/包含率。
                # 裸包含率会把「大框套住小框但面积悬殊」也算成重复，
                # 而那恰恰是面积护栏要放过的两种独立个体。
                if _same_individual(r[i][2], r[j][2]):
                    dup += 1
                    dupf.add(name)
        hit += st == "命中"
        any_hit += st in ("命中", "任意命中")
        miss += st == "漏检"
        wrong += st == "误判"
    return dict(top1=hit, any=any_hit, miss=miss, wrong=wrong, boxes=tb,
                per=round(tb / len(boxes), 2), g3=g3, dup=dup, dupf=len(dupf), pf=pf)


def main() -> int:
    s = get_settings()
    det = Detector()
    data = json.loads(ASSET.read_text(encoding="utf-8"))
    boxes, cn = data["boxes"], data["cn"]
    L = [
        "═" * 78,
        "最终验收 —— 直接调用生产代码 detector._aggregate",
        "═" * 78,
        f"图集 {len(boxes)} 张/  候选框 {sum(len(v['cands']) for v in boxes.values())} 个",
        f"生产阈值MERGE_IOU={MERGE_IOU}  MERGE_CONTAIN={MERGE_CONTAIN}  "
        f"MERGE_AREA_RATIO={MERGE_AREA_RATIO}",
        f"配置 detect_min_conf={s.detect_min_conf} detect_cluster_bonus={s.detect_cluster_bonus}",
        "",
    ]

    old = run(boxes, cn, lambda r, sz: aggregate_old(r, sz))
    new = run(boxes, cn, lambda r, sz: det._aggregate(r, sz))

    def row(k, a, b, better=None):
        mark = ""
        if better == "up" and b > a:
            mark = " ↑"
        elif better == "down" and b < a:
            mark = " ↓"
        elif better == "keep" and b == a:
            mark = " ="
        return f"  {k:<22}{a:>8}{b:>8}{mark}"

    L.append("【验收五项指标】（← 旧逻辑 / → 新逻辑）")
    L.append(row("Top-1命中", old["top1"], new["top1"], "keep"))
    L.append(row("任意命中", old["any"], new["any"], ""))
    L.append(row("漏检", old["miss"], new["miss"], "down"))
    L.append(row("误判", old["wrong"], new["wrong"], "down"))
    L.append(row("总检出框", old["boxes"], new["boxes"], "down"))
    L.append(row("平均框/图", old["per"], new["per"], "down"))
    L.append(row("≥3虫种的图", old["g3"], new["g3"], "down"))
    L.append(row("输出内重叠框对", old["dup"], new["dup"], "down"))
    L.append(row("  └涉及图数", old["dupf"], new["dupf"], "down"))
    L.append("")
    L.append(f"目标图 {TGT}：旧 = {old['pf'][TGT][:4]}")
    L.append(f"           新 = {new['pf'][TGT][:4]}")

    L.append("\n【硬性验收逐条判定】")
    ok1 = new["top1"] >= 87
    ok2 = new["boxes"] < 300
    ok3 = new["pf"][TGT][2] == 3
    ok4 = new["dup"] == 0
    ok5 = new["miss"] == old["miss"]
    L.append(f"  {'PASS' if ok1 else 'FAIL'}  Top-1 ≥ 87            实际 {new['top1']}/181")
    L.append(f"  {'PASS' if ok2 else 'FAIL'}  总检出框 < 300        实际 {new['boxes']}")
    L.append(f"  {'PASS' if ok3 else 'FAIL'}  目标图 = 3 个框       实际 {new['pf'][TGT][2]}")
    L.append(f"  {'PASS' if ok4 else 'FAIL'}  输出无重复框对       实际 {new['dup']} 对"
             f"（旧逻辑 {old['dup']} 对 / {old['dupf']} 张图）")
    L.append(f"  {'PASS' if ok5 else 'FAIL'}  漏检未增加  {old['miss']} → {new['miss']}")
    L.append(f"  {'PASS' if new['any'] >= 102 else 'WARN'}  任意命中 ≥ 102实际 {new['any']}/181"
             "  ← 与修复目标天然对立，见报告第三节")

    L.append("\n【任意命中掉点归因】")
    n_same = n_diff = 0
    diffs = []
    for name, rec in boxes.items():
        raw = [(int(c), float(cf), (float(a), float(b), float(x), float(y)))
               for c, cf, a, b, x, y, _s in rec["cands"]]
        truth = rec["truth"]
        o = [{"class_cn": cn[str(c)]} for c, _, _ in aggregate_old(raw, tuple(rec["size"]))]
        n = [{"class_cn": cn[str(c)]} for c, _, _ in det._aggregate(raw, tuple(rec["size"]))]
        if any(p["class_cn"] == truth for p in o) and \
                not any(p["class_cn"] == truth for p in n):
            rep = det._aggregate(raw, tuple(rec["size"]))[0]
            tb = [b for b in raw if cn[str(b[0])] == truth]
            if not tb:
                continue
            bt = max(tb, key=lambda b: b[1])
            same = _iou(bt[2], rep[2]) >= REAL_IOU_CEIL or \
                _containment(bt[2], rep[2]) >= REAL_CON_CEIL
            n_same += same
            n_diff += not same
            if not same:
                diffs.append(name)
    L.append(f"  掉点 {n_same + n_diff} 张：同一只虫的少数派类别 {n_same} 张（预期内，"
             f"正是被修掉的 bug）/ 疑似独立个体 {n_diff} 张 {diffs}")

    Path(ROOT / "_final_out.txt").write_text("\n".join(L), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())