# -*- coding: utf-8 -*-
"""实验七：目视校验素材准备。

前六轮的数字都在证明「算法层面的分离度」，但有一类风险数字回答不了：
**把两只真虫误并成一只**。这类错误在指标上可能只表现为「框数变少」，
看不出来。所以必须画到图上，用眼睛数。

产出：
  1) _vis_candidates.txt —— 按「空间簇数」排序，挑出多虫候选图
  2) _vis/<图名>.jpg     —— 左=旧逻辑 右=新逻辑，同图并排画框
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from ab_dedup import _aggregate_old, _containment, _iou  # noqa: E402

ASSET = Path(r"D:\ai搭建\2026-10-06-16-15-16\_boxes2.json")
IMG_ROOT = Path(r"D:\pestguard\_外部验证集\网图人工复核")
OUT_DIR = ROOT / "_vis"

IOU_T, CON_T = 0.30, 0.50
COLORS = [(255, 48, 48), (0, 200, 255), (255, 210, 0), (80, 255, 80),
          (255, 120, 255), (255, 160, 0), (0, 128, 255), (200, 255, 0)]


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


def aggregate_new(raw, min_conf=0.30):
    keep = []
    for c in clusters_seeded(raw, IOU_T, CON_T):
        if max(b[1] for b in c) < min_conf:
            continue
        keep.append(max(c, key=lambda b: b[1]))
    return keep


def find_image(name: str) -> Path | None:
    for p in IMG_ROOT.rglob(name):
        return p
    return None


def draw(panel: Image.Image, ranked, cn, tag: str) -> Image.Image:
    d = ImageDraw.Draw(panel)
    for i, (cls, conf, bx) in enumerate(ranked):
        col = COLORS[i % len(COLORS)]
        d.rectangle([bx[0], bx[1], bx[2], bx[3]], outline=col, width=4)
        label = f"{i+1}.{cn[str(cls)]} {conf:.2f}"
        tw = d.textlength(label)
        ty = max(0, bx[1] - 20)
        d.rectangle([bx[0], ty, bx[0] + tw + 8, ty + 20], fill=col)
        d.text((bx[0] + 4, ty + 3), label, fill=(0, 0, 0))
    d.rectangle([0, 0, panel.width - 1, 28], fill=(0, 0, 0))
    d.text((8, 7), f"{tag}  n={len(ranked)}", fill=(255, 255, 255))
    return panel


def main() -> int:
    data = json.loads(ASSET.read_text(encoding="utf-8"))
    boxes, cn = data["boxes"], data["cn"]
    OUT_DIR.mkdir(exist_ok=True)

    rows = []
    for name, rec in boxes.items():
        raw = [(int(c), float(cf), (float(a), float(b), float(x), float(y)))
               for c, cf, a, b, x, y, _s in rec["cands"]]
        cl = clusters_seeded(raw, IOU_T, CON_T)
        strong = [c for c in cl if max(b[1] for b in c) >= 0.30]
        old = _aggregate_old(raw, tuple(rec["size"]))
        new = aggregate_new(raw)
        rows.append((len(strong), len(old), len(new), name, len(raw)))
    rows.sort(reverse=True)

    lines = ["簇数 旧框 新框 候选 图片名", ""]
    for ncl, no, nn, name, ncand in rows[:30]:
        lines.append(f"{ncl:>4} {no:>4} {nn:>4} {ncand:>6}  {name}")
    lines.append("\n=== 目标图 ===")
    for ncl, no, nn, name, ncand in rows:
        if "稻纵卷叶螟_04" in name:
            lines.append(f"{ncl:>4} {no:>4} {nn:>4} {ncand:>6}  {name}")

    # 画图：目标图 + 簇数最多的 8 张
    todo = [r[3] for r in rows if r[0] >= 3][:8]
    if "稻纵卷叶螟_04.jpg" in boxes:
        todo = ["稻纵卷叶螟_04.jpg"] + todo
    lines.append(f"\n已画图：{todo}")
    for name in todo:
        src = find_image(name)
        if src is None:
            lines.append(f"  [跳过] 找不到原图 {name}")
            continue
        rec = boxes[name]
        raw = [(int(c), float(cf), (float(a), float(b), float(x), float(y)))
               for c, cf, a, b, x, y, _s in rec["cands"]]
        im = Image.open(src).convert("RGB")
        old = _aggregate_old(raw, tuple(rec["size"]))
        new = aggregate_new(raw)
        a = draw(im.copy(), old, cn, "OLD")
        b = draw(im.copy(), new, cn, "NEW")
        gap = 12
        canvas = Image.new("RGB", (a.width + b.width + gap, max(a.height, b.height)),
                           (30, 30, 30))
        canvas.paste(a, (0, 0))
        canvas.paste(b, (a.width + gap, 0))
        canvas.save(OUT_DIR / f"{Path(name).stem}.jpg", quality=88)
        lines.append(f"  {name}: old={len(old)} new={len(new)}")

    (ROOT / "_vis_candidates.txt").write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())