# -*- coding: utf-8 -*-
"""把 _qa_result.json 汇总成人读的表格。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R = json.loads((ROOT / "_qa_result.json").read_text(encoding="utf-8"))
L: list[str] = []
w = L.append

w("=" * 92)
w("QA 独立验收 —— 严过关自己重跑的数字")
w("=" * 92)
m = R["meta"]
w(f"图集 {m['n_images']}张 / 候选框 {m['n_cands']} 个")
w(f"配置 min_conf={m['detect_min_conf']} bonus={m['detect_cluster_bonus']} "
  f"IOU={m['MERGE_IOU']} CONTAIN={m['MERGE_CONTAIN']} AREA={m['MERGE_AREA_RATIO']}")
w(f"自写几何判据 vs 生产判据 最大偏差 = {m['geo_crosscheck_max_err']:.2e}（应≈0）")
w("")

hdr = ("变体", "Top-1", "任意命中", "漏检", "误判", "总框", "框/图", "≥3虫种", "重复框对", "涉及图")
w("  ".join(f"{h:>9}" for h in hdr))


def line(tag, d):
    return "  ".join(f"{v:>9}" for v in (
        tag, d["top1"], d["any"], d["miss"], d["wrong"], d["boxes"],
        d["per_img"], d["ge3"], d["dup"], d["dup_files"]))


for key, tag in (("new_prod", "新逻辑(生产)"), ("old_replica", "旧逻辑复刻"),
                 ("old_replica_no_cross", "旧逻辑-无跨类别抑制"),
                 ("old_replica_con070", "旧逻辑contain0.7"),
                 ("old_replica_con070_no_cross", "旧逻辑c0.7无跨抑制")):
    w(line(tag, R[key]))
w("")
w("【历史数字对照】文档里出现过的三个数，看复刻能对上哪个：")
w(f"  337 框 / 102 任意命中 / 18 漏检 / 87 Top-1  ← 软件设计文档「错位重复框合并」阶段")
w(f"  425 框 / 跨类别空间抑制阶段（文档软件设计文档.md）")
w(f"  复刻(0.6/0.35+跨抑制) = {R['old_replica']['boxes']} 框 / 任意 {R['old_replica']['any']}")
w(f"  复刻(0.6/0.35无跨抑制) = {R['old_replica_no_cross']['boxes']} 框 / 任意 {R['old_replica_no_cross']['any']}")
w(f"  复刻(0.6/0.70+跨抑制) = {R['old_replica_con070']['boxes']} 框 / 任意 {R['old_replica_con070']['any']}")
w(f"  复刻(0.6/0.70无跨抑制) = {R['old_replica_con070_no_cross']['boxes']} 框 / 任意 {R['old_replica_con070_no_cross']['any']}")
w("")

w("【任意命中掉点 / 涨点】")
w(f"  掉点{len(R['dropped'])} 张：{R['dropped']}")
w(f"  涨点 {len(R['gained'])} 张：{R['gained']}")
w("")

w("【掉点逐张明细】旧判定 → 新判定")
det = R["detail_new"]
for name in R["dropped"]:
    t = det[name]["truth"]
    o = R["detail_old"][name]
    n = det[name]
    ostr = " / ".join(f"{p['cn']}:{p['conf']:.2f}" for p in o["preds"]) or "(无)"
    nstr = " / ".join(f"{p['cn']}:{p['conf']:.2f}" for p in n["preds"]) or "(无)"
    w(f"\n  ▸ {name}   真值={t}")
    w(f"     旧 {o['n_out']}框 [{ostr}]")
    w(f"     新 {n['n_out']}框 [{nstr}]")
    w(f"     候选 {n['n_cands']} 个 / 空间簇 {n['n_clusters_raw']} 个 / "
      f"过阈簇 {n['n_clusters_strong']} 个")
w("")

w("【3x3 阈值敏感度矩阵】（生产代码，改常量后复原）")
w("  iou\\con" + "".join(f"{c:>10.2f}" for c in (0.45, 0.50, 0.55)))
for i in (0.25, 0.30, 0.35):
    cells = []
    for c in (0.45, 0.50, 0.55):
        g = next(x for x in R["grid_3x3"] if x["iou"] == i and x["contain"] == c)
        cells.append(f"{g['top1']}/{g['any']}/{g['boxes']}/{g['dup']}")
    w(f"  {i:.2f}   " + "".join(f"{v:>10}" for v in cells))
w("  单元格 = Top-1 / 任意命中 / 总框 / 输出内重复框对")
w("")
w("  完整明细：")
w("  iou  contain  Top1  任意  漏检  误判  总框框/图 ≥3种 重复对 涉及图")
for g in R["grid_3x3"]:
    w(f"  {g['iou']:.2f}{g['contain']:>8.2f}{g['top1']:>6}{g['any']:>6}"
      f"{g['miss']:>6}{g['wrong']:>6}{g['boxes']:>7}{g['per_img']:>6}"
      f"{g['ge3']:>6}{g['dup']:>6}{g['dup_files']:>7}")
w("")

w("【面积护栏 A/B】(IoU=0.30, contain=0.50)")
w("  护栏     Top-1  任意  漏检  误判  总框  框/图  ≥3种 重复对 涉及图")
for g in R["area_guard_ab"]:
    ar = g["area_ratio"]
    ar = "关闭" if ar == "off" else f"{float(ar):.1f}"
    w(f"  {ar:>6}{g['top1']:>7}{g['any']:>6}{g['miss']:>6}{g['wrong']:>6}"
      f"{g['boxes']:>7}{g['per_img']:>6}{g['ge3']:>6}{g['dup']:>6}{g['dup_files']:>7}")
w("")

# ── 多虫图候选清单（供目视抽检）────────────────────────────
w("【多虫图候选（按过阈簇数排序）—— 目视抽检用】")
w(" 簇数 旧框 新框 候选 图片名真值")
rows = []
for name, d in det.items():
    rows.append((d["n_clusters_strong"], R["detail_old"][name]["n_out"],
                 d["n_out"], d["n_cands"], name, d["truth"]))
rows.sort(reverse=True)
for r in rows[:40]:
    w(f"{r[0]:>4}{r[1]:>5}{r[2]:>5}{r[3]:>7}  {r[4]}{r[5]}")
w("")

(ROOT / "_qa_report.txt").write_text("\n".join(L), encoding="utf-8")
print("written")