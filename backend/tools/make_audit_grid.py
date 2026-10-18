# -*- coding: utf-8 -*-
"""图像数据集「标注质量」快速核验工具

用途
----
把一整批图片压成可通览的拼图，供人（或多模态模型）在很短时间内
逐张检查两件事：

  A. 底部条带图 —— 查图片底部有没有**图注文字 / 版权水印 / 图库标签**
  B. 缩略网格图 —— 查**图片内容与文件名标注是否相符**

为什么需要它
------------
233 张图逐张打开看不现实；拼成 10 张网格后 10 次就能看完。
实测用这个办法抓出了：图里是蚂蚁却标"盲蝽"、图里只有虫道没有虫、
以及 6 张带商业摄影师水印的图。

用法
----
    python tools/make_audit_grid.py --dir "D:/path/to/images" --out "D:/path/out"

    --dir     待检图片目录（不递归，只看本层）
    --out     输出目录（自动创建）
    --batch-a 底部条带每张拼多少图（默认 15）
    --batch-b 缩略网格每张拼多少图（默认 25）
    --frac-a  底部条带取图片高度的比例（默认 0.20）

输出
----
    A底部_01.jpg ...   底部条带拼图
    B缩略_01.jpg ...   缩略网格拼图（5 列）

注意
----
本机存在「每轮删除限额」（累计删除约 50 个文件会触发安全策略并中断进程），
所以本脚本**只写不删**。重跑会覆盖同名文件，不会堆积垃圾。
"""
import argparse
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]


def load_font(size: int = 20):
    for fp in FONT_CANDIDATES:
        if Path(fp).exists():
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    print("!! 未找到中文字体，标签可能显示为方块", file=sys.stderr)
    return ImageFont.load_default()


def collect(img_dir: Path):
    return sorted(
        p for p in img_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )


def bottom_strip(path: Path, width: int, frac: float):
    """截取图片底部 frac 比例，缩放到统一宽度"""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    crop = im.crop((0, int(h * (1 - frac)), w, h))
    cw, ch = crop.size
    return crop.resize((width, max(1, int(ch * width / cw))), Image.LANCZOS)


def build_strips(files, out: Path, width: int, frac: float, batch: int, font):
    bar = 28
    for bi in range(0, len(files), batch):
        blocks = []
        for p in files[bi:bi + batch]:
            lab = Image.new("RGB", (width, bar), (0, 0, 0))
            ImageDraw.Draw(lab).text((8, 4), p.stem, fill=(255, 220, 0), font=font)
            blocks.append(lab)
            try:
                blocks.append(bottom_strip(p, width, frac))
            except Exception as exc:  # noqa: BLE001
                print("  跳过", p.name, exc)
        total = sum(b.size[1] for b in blocks) + 4 * len(blocks)
        canvas = Image.new("RGB", (width, total), (40, 40, 40))
        y = 0
        for b in blocks:
            canvas.paste(b, (0, y))
            y += b.size[1] + 4
        f = out / f"A底部_{bi // batch + 1:02d}.jpg"
        canvas.save(f, quality=90)
    return math.ceil(len(files) / batch)


def build_grid(files, out: Path, cols: int, tw: int, ch: int, batch: int, font):
    bar = 26
    for bi in range(0, len(files), batch):
        chunk = files[bi:bi + batch]
        rows = math.ceil(len(chunk) / cols)
        canvas = Image.new("RGB", (cols * tw, rows * (ch + bar)), (25, 25, 25))
        d = ImageDraw.Draw(canvas)
        for i, p in enumerate(chunk):
            r, c = divmod(i, cols)
            ox, oy = c * tw, r * (ch + bar)
            try:
                im = Image.open(p).convert("RGB")
                im.thumbnail((tw - 10, ch - 8), Image.LANCZOS)
                canvas.paste(im, (ox + (tw - im.size[0]) // 2, oy + (ch - im.size[1]) // 2))
            except Exception as exc:  # noqa: BLE001
                print("  跳过", p.name, exc)
            d.text((ox + 6, oy + ch + 3), p.stem, fill=(255, 220, 0), font=font)
        f = out / f"B缩略_{bi // batch + 1:02d}.jpg"
        canvas.save(f, quality=88)
    return math.ceil(len(files) / batch)


def main():
    ap = argparse.ArgumentParser(description="图像数据集标注质量快速核验")
    ap.add_argument("--dir", required=True, help="待检图片目录")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--batch-a", type=int, default=15, help="底部条带每图张数")
    ap.add_argument("--batch-b", type=int, default=25, help="缩略网格每图张数")
    ap.add_argument("--frac-a", type=float, default=0.20, help="底部条带占高度比例")
    args = ap.parse_args()

    src = Path(args.dir)
    out = Path(args.out)
    if not src.is_dir():
        print("目录不存在:", src)
        return 1
    out.mkdir(parents=True, exist_ok=True)

    files = collect(src)
    if not files:
        print("没有可用图片:", src)
        return 1
    print(f"图片总数: {len(files)}")
    font = load_font(20)

    na = build_strips(files, out, 1000, args.frac_a, args.batch_a, font)
    print(f"A. 底部条带 {na} 张")
    nb = build_grid(files, out, 5, 260, 200, args.batch_b, font)
    print(f"B. 缩略网格 {nb} 张")
    print("输出目录:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
