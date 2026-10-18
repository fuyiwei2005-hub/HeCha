# -*- coding: utf-8 -*-
"""QA 独立目视校验：把「新逻辑实际输出」画到原图上，输出大图供人眼数虫。

与 tools/vis_dedup.py 的区别：
  1. 框来自生产代码detector._aggregate（不是抄本）；
  2. 左图原图无标注，右图新逻辑标注，中间额外画出**被吸进同一簇但没出框的候选**，
     便于判断「是不是把两只真虫并成了一只」；
  3. 每张图下方打印真值/ 输出框数 / 空间簇数 / 候选数。

产出：_qa_vis/<图名>.jpg  以及 _qa_vis_index.txt
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings            # noqa: E402
from app.services import detector as D              # noqa: E402

ASSET = Path(r"D:\ai搭建\2026-10-06-16-15-16\_boxes2.json")
IMG_ROOT = Path(r"D:\pestguard\_外部验证集\网图人工复核")
OUT_DIR = ROOT / "_qa_vis"

GREEN = (0, 230, 0)
RED = (255, 40, 40)
GREY = (150, 150, 150)


def find_image(name: str) -> Path | None:
    for p in IMG_ROOT.rglob(name):
        return p
    return None


def main() -> int:
    names = sys.argv[1:]
    s = get_settings()
    det = D.Detector()
    data = json.loads(ASSET.read_text(encoding="utf-8"))
    boxes, cn = data["boxes"], data["cn"]
    OUT_DIR.mkdir(exist_ok=True)

    idx: list[str] = []
    for name in names:
        if name not in boxes:
            idx.append(f"[跳过] 资产里没有 {name}")
            continue
        rec = boxes[name]
        raw = [(int(c), float(cf), (float(a), float(b), float(x), float(y)), src)
               for c, cf, a, b, x, y, src in rec["cands"]]
        ranked = det._aggregate([(c, f, b) for c, f, b, _s in raw], tuple(rec["size"]))
        clusters = D._cluster_individuals([(c, f, b) for c, f, b, _s in raw])
        src = find_image(name)
        if src is None:
            idx.append(f"[跳过] 找不到原图 {name}")
            continue
        im = Image.open(src).convert("RGB")

        # ── 左：原图 +空间簇编号（每簇一个颜色，看得出有几簇）──
        left = im.copy()
        d = ImageDraw.Draw(left)
        for i, cl in enumerate(clusters):
            bx = max(cl, key=lambda b: b[1])[2]
            col = (255, 255, 255) if i % 2 == 0 else (0, 0, 0)
            d.rectangle(bx, outline=col, width=5)
            d.text((bx[0] + 4, bx[1] + 4), f"C{i}", fill=col)
        d.rectangle([0, 0, left.width - 1, 30], fill=(0, 0, 0))
        d.text((8, 8), f"clusters={len(clusters)}  cands={len(raw)}  "
                       f"truth={rec['truth']}", fill=(255, 255, 0))

        # ── 右：实际输出框 ──
        right = im.copy()
        d2 = ImageDraw.Draw(right)
        for i, (c, f, b) in enumerate(ranked):
            d2.rectangle(b, outline=GREEN, width=5)
            lbl = f"OUT{i} {cn[str(c)]} {f:.2f}"
            wdt = d2.textlength(lbl)
            ty = max(0, b[1] - 22)
            d2.rectangle([b[0], ty, b[0] + wdt + 8, ty + 22], fill=GREEN)
            d2.text((b[0] + 4, ty + 4), lbl, fill=(0, 0, 0))
        # 画被淘汰的候选（灰），看它们落在哪
        out_boxes = [b[2] for b in ranked]
        for c, f, b, sname in raw:
            if any(b is ob for ob in out_boxes):
                continue
            hit = any(D._containment(ob, b) >= 0.5 or D._iou(ob, b) >= 0.3 for ob in out_boxes)
            d2.rectangle(b, outline=(GREY if hit else RED), width=2)
        d2.rectangle([0, 0, right.width - 1, 30], fill=(0, 0, 0))
        d2.text((8, 8), f"NEW output n={len(ranked)}  "
                        f"(grey=absorbed  red=dropped-not-in-any-output)", fill=(0, 255, 0))

        gap = 10
        canvas = Image.new("RGB", (left.width + right.width + gap,
                                   max(left.height, right.height) + 34), (25, 25, 25))
        canvas.paste(left, (0, 34))
        canvas.paste(right, (left.width + gap, 34))
        d3 = ImageDraw.Draw(canvas)
        d3.text((6, 6), f"{name}   truth={rec['truth']}   "
                        f"clusters={len(clusters)} cands={len(raw)} NEW_out={len(ranked)}",
                fill=(255, 255, 255))
        canvas.save(OUT_DIR / f"{Path(name).stem}.jpg", quality=90)

        # ── 文本：逐簇明细，供核对 ──
        idx.append("=" * 70)
        idx.append(f"{name}   真值={rec['truth']}  空间簇={len(clusters)}  "
                   f"候选={len(raw)}  新输出={len(ranked)}")
        for i, cl in enumerate(sorted(clusters, key=lambda c: -max(x[1] for x in c))):
            best = max(cl, key=lambda b: b[1])
            others = sorted(((b[1], cn[str(b[0])], sname) for b, sname in
                             [(x, dict(zip(range(len(raw)), [q[3] for q in raw]))[j])
                              for j, x in enumerate(cl)]), reverse=True)
            desc = " / ".join(f"{c}:{cf:.2f}({sn})" for cf, c, sn in others)
            area = D._area(best[2])
            idx.append(f"  C{i}: best={cn[str(best[0])]} {best[1]:.4f} "
                       f"box=({best[2][0]:.0f},{best[2][1]:.0f},"
                       f"{best[2][2]:.0f},{best[2][3]:.0f}) area={area:.0f}px  n={len(cl)}")
            idx.append(f"      成员: {desc}")
            idx.append(f"      → 是否输出: {'是' if any(best[2] is ob for ob in out_boxes) else '否(簇内最高conf<%.2f)' % s.detect_min_conf}")
    (ROOT / "_qa_vis_index.txt").write_text("\n".join(idx), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())