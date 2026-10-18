#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Markdown → PDF 转换工具（参赛材料专用）

用途：把 `docs/参赛材料/*.md` 转成官方要求的 PDF 文件。
设计文档缺 PDF = 作品无效（官方原文），所以这个脚本是硬性交付链路的一环。

支持的 Markdown 子集（够用即可，不追求完整 CommonMark）：
  - ATX 标题 # ## ### ####
  - 段落 / 空行分段
  - 无序列表 - * +，支持两级缩进
  - 有序列表 1. 2.
  - 表格（GFM 管道表，自动识别表头分隔行）
  - 围栏代码块 ```lang
  - 引用块 >
  - 分隔线 ---
  - 行内加粗 **x** 与行内代码 `x`

用法：
    python tools/md2pdf.py <输入.md> <输出.pdf>
    python tools/md2pdf.py --all          # 批量转换参赛材料目录下全部 md
"""

import argparse
import os
import re
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, CondPageBreak, Frame, Image as RLImage, PageBreak,
    PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

# ---------- 字体 ----------
FONT_DIR = r"C:\Windows\Fonts"
_FONTS = {}


def register_fonts():
    """注册中文字体。微软雅黑为主字体，黑体作标题。"""
    try:
        pdfmetrics.registerFont(TTFont("CN", os.path.join(FONT_DIR, "msyh.ttc")))
        pdfmetrics.registerFont(TTFont("CN-Bold", os.path.join(FONT_DIR, "msyhbd.ttc")))
        _FONTS["body"] = "CN"
        _FONTS["bold"] = "CN-Bold"
    except Exception:
        # 回退：宋体 + 黑体
        pdfmetrics.registerFont(TTFont("CN", os.path.join(FONT_DIR, "simsun.ttc")))
        pdfmetrics.registerFont(TTFont("CN-Bold", os.path.join(FONT_DIR, "simhei.ttf")))
        _FONTS["body"] = "CN"
        _FONTS["bold"] = "CN-Bold"
    pdfmetrics.registerFontFamily("CN", normal="CN", bold="CN-Bold")


# ---------- 样式 ----------
def build_styles():
    base = getSampleStyleSheet()
    s = {}

    s["title"] = ParagraphStyle(
        "title", parent=base["Title"], fontName=_FONTS["bold"],
        fontSize=22, leading=32, spaceAfter=6, alignment=TA_CENTER,
        textColor=colors.HexColor("#1a1a1a"),
    )
    s["subtitle"] = ParagraphStyle(
        "subtitle", parent=base["Normal"], fontName=_FONTS["body"],
        fontSize=13, leading=20, spaceAfter=4, alignment=TA_CENTER,
        textColor=colors.HexColor("#444444"),
    )
    s["h1"] = ParagraphStyle(
        "h1", parent=base["Heading1"], fontName=_FONTS["bold"],
        fontSize=16, leading=24, spaceBefore=16, spaceAfter=8,
        textColor=colors.HexColor("#0f3d2e"),
    )
    s["h2"] = ParagraphStyle(
        "h2", parent=base["Heading2"], fontName=_FONTS["bold"],
        fontSize=13.5, leading=20, spaceBefore=12, spaceAfter=6,
        textColor=colors.HexColor("#14503a"),
    )
    s["h3"] = ParagraphStyle(
        "h3", parent=base["Heading3"], fontName=_FONTS["bold"],
        fontSize=12, leading=18, spaceBefore=9, spaceAfter=4,
        textColor=colors.HexColor("#1a1a1a"),
    )
    s["h4"] = ParagraphStyle(
        "h4", parent=base["Heading4"], fontName=_FONTS["bold"],
        fontSize=11, leading=17, spaceBefore=7, spaceAfter=3,
    )
    s["body"] = ParagraphStyle(
        "body", parent=base["Normal"], fontName=_FONTS["body"],
        fontSize=10.5, leading=17.5, alignment=TA_JUSTIFY,
        spaceAfter=5, firstLineIndent=0,
    )
    s["li"] = ParagraphStyle(
        "li", parent=s["body"], leftIndent=14, bulletIndent=4, spaceAfter=2.5,
    )
    s["quote"] = ParagraphStyle(
        "quote", parent=s["body"], leftIndent=14,
        textColor=colors.HexColor("#555555"), borderPadding=(0, 0, 0, 6),
        backColor=colors.HexColor("#f4f6f5"), spaceBefore=4, spaceAfter=6,
    )
    s["code"] = ParagraphStyle(
        "code", parent=base["Code"], fontName="Courier", fontSize=8.5,
        leading=12, leftIndent=10, backColor=colors.HexColor("#f6f6f6"),
        borderPadding=5, spaceBefore=4, spaceAfter=6,
    )
    s["cell"] = ParagraphStyle(
        "cell", parent=base["Normal"], fontName=_FONTS["body"],
        fontSize=9, leading=13.5,
    )
    s["cell_head"] = ParagraphStyle(
        "cell_head", parent=s["cell"], fontName=_FONTS["bold"],
    )
    return s


# ---------- 行内解析 ----------
def esc(t: str) -> str:
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return t


def inline(t: str, s) -> str:
    """转义后还原行内 Markdown。顺序：先抽出行内代码占位，避免内部被二次处理。"""
    codes = []

    def stash(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    t = re.sub(r"`([^`]+)`", stash, t)
    t = esc(t)
    t = re.sub(r"\*\*([^*]+)\*\*", r'<b>\1</b>', t)
    t = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<u>\1</u>', t)
    for i, c in enumerate(codes):
        t = t.replace(f"\x00{i}\x00", f'<font face="Courier" size="8.5">{esc(c)}</font>')
    return t


# ---------- 块级解析 ----------
def parse_blocks(md: str):
    lines = md.replace("\r\n", "\n").split("\n")
    blocks, i, n = [], 0, len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # 围栏代码块
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            body = esc("\n".join(buf)) if lang else esc("\n".join(buf)).replace("\n", "<br/>")
            blocks.append(("code", body))
            continue

        # 表格：当前行含 |，且下一行是分隔行
        if "|" in stripped and i + 1 < n and re.match(
            r"^\s*\|?[\s:\-|]+\|[\s:\-|]*$", lines[i + 1]
        ):
            header = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2
            rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            blocks.append(("table", (header, rows)))
            continue

        # 分隔线
        if re.match(r"^-{3,}$|^\*{3,}$|^_{3,}$", stripped):
            blocks.append(("hr", None))
            i += 1
            continue

        # 图片 ![alt](path)
        m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", stripped)
        if m:
            alt, src = m.group(1), m.group(2)
            blocks.append(("image", (alt, src)))
            i += 1
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            blocks.append((f"h{len(m.group(1))}", m.group(2).strip()))
            i += 1
            continue

        # 引用块
        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            blocks.append(("quote", " ".join(x for x in buf if x)))
            continue

        # 列表
        if re.match(r"^([-*+]|\d+\.)\s+", stripped):
            items = []
            while i < n and re.match(r"^\s*([-*+]|\d+\.)\s+", lines[i]):
                raw = lines[i]
                indent = len(raw) - len(raw.lstrip())
                content = re.sub(r"^\s*([-*+]|\d+\.)\s+", "", raw).strip()
                items.append((indent >= 2, content))
                i += 1
            blocks.append(("list", items))
            continue

        # 段落：吃到空行或下一个块级标记
        buf = [stripped]
        i += 1
        while i < n:
            nxt = lines[i].strip()
            if (not nxt or nxt.startswith(("#", ">", "```", "|", "---", "!["))or re.match(r"^([-*+]|\d+\.)\s+", nxt)):
                break
            buf.append(nxt)
            i += 1
        blocks.append(("p", " ".join(buf)))

    return blocks


# ---------- 渲染 ----------
def render(md: str, out_pdf: str, s, base_dir: str = None):
    doc = BaseDocTemplate(
        out_pdf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=18 * mm,
        title="PestGuard 软件设计文档", author="PestGuard 团队",
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height, id="body",
    )

    def on_page(canvas, d):
        canvas.saveState()
        canvas.setFont(_FONTS["body"], 8)
        canvas.setFillColor(colors.HexColor("#888888"))
        # 页眉
        canvas.drawString(doc.leftMargin, A4[1] - 12 * mm, "PestGuard 农作物害虫智能识别与防治决策系统")
        # 页脚页码
        canvas.drawCentredString(A4[0] / 2, 10 * mm, f"第 {canvas.getPageNumber()} 页")
        canvas.setStrokeColor(colors.HexColor("#cccccc"))
        canvas.setLineWidth(0.4)
        canvas.line(doc.leftMargin, A4[1] - 14 * mm, A4[0] - doc.rightMargin, A4[1] - 14 * mm)
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=on_page)])

    story = []
    first_title = True
    for kind, payload in parse_blocks(md):
        if kind == "title":
            story.append(Paragraph(inline(payload, s), s["title"]))
            first_title = False
        elif kind == "subtitle":
            story.append(Paragraph(inline(payload, s), s["subtitle"]))
        elif kind in ("h1", "h2", "h3", "h4"):
            # 文档里第一个 h1 其实是封面主标题
            story.append(Paragraph(inline(payload, s), s[kind]))
            story.append(Spacer(1, 2))
        elif kind == "p":
            story.append(Paragraph(inline(payload, s), s["body"]))
        elif kind == "quote":
            story.append(Paragraph(inline(payload, s), s["quote"]))
        elif kind == "code":
            story.append(Paragraph(payload, s["code"]))
        elif kind == "image":
            alt, src = payload
            path = src if os.path.isabs(src) else os.path.join(base_dir or ".", src)
            if os.path.exists(path):
                try:
                    from PIL import Image as PILImage
                    with PILImage.open(path) as im:
                        iw, ih = im.size
                    max_w = doc.width
                    max_h = 150 * mm  # 留出标题与图注空间，避免图被切到下一页
                    scale = min(max_w / iw, max_h / ih, 1.0)
                    w, h = iw * scale, ih * scale
                    story.append(RLImage(path, width=w, height=h))
                    if alt:
                        cap = ParagraphStyle(
                            "cap", parent=s["body"], fontSize=8.5,
                            alignment=TA_CENTER, textColor=colors.HexColor("#777777"),
                            spaceBefore=3,
                        )
                        story.append(Paragraph(inline(alt, s), cap))
                    story.append(Spacer(1, 10))
                    # 保证图与图注成组，不被分页拆开
                    story.append(CondPageBreak(90 * mm))
                except Exception as e:
                    story.append(Paragraph(
                        f"[图片无法嵌入：{esc(os.path.basename(path))} — {type(e).__name__}]",
                        s["body"]))
            else:
                story.append(Paragraph(
                    f"[图片缺失：{esc(src)}]", s["body"]))
        elif kind == "hr":
            story.append(Spacer(1, 6))
        elif kind == "list":
            for ordered, content in payload:
                st = ParagraphStyle(
                    "li2", parent=s["li"], leftIndent=28, bulletIndent=16,
                )
                story.append(Paragraph(inline(content, s),
                                       st if ordered else s["li"],
                                       bulletText="–" if ordered else "•"))
        elif kind == "table":
            header, rows = payload
            ncol = len(header)
            avail = doc.width
            data = [[Paragraph(inline(c, s), s["cell_head"]) for c in header]]
            for r in rows:
                r = (r + [""] * ncol)[:ncol]
                data.append([Paragraph(inline(c, s), s["cell"]) for c in r])

            # 按内容长度分配列宽
            weights = []
            for c in range(ncol):
                lens = [len(str(header[c]))] + [len(str(r[c])) if c < len(r) else 0 for r in rows]
                weights.append(max(6, min(60, max(lens))))
            total = sum(weights)
            widths = [avail * w / total for w in weights]

            t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f0ec")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f3d2e")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b8c8c0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#f7faf8")]),
            ]))
            story.append(t)
            story.append(Spacer(1, 7))

    doc.build(story)


def convert(src: str, dst: str, s) -> int:
    with open(src, encoding="utf-8") as f:
        md = f.read()
    # 首行 # 降级为封面标题
    lines = md.split("\n")
    if lines and lines[0].startswith("# "):
        lines[0] = "#TITLE " + lines[0][2:]
    md = "\n".join(lines).replace("#TITLE ", "")
    render(md, dst, s, base_dir=os.path.dirname(os.path.abspath(src)))
    return os.path.getsize(dst)


def main() -> int:
    register_fonts()
    s = build_styles()

    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?")
    ap.add_argument("dst", nargs="?")
    ap.add_argument("--all", action="store_true", help="批量转换参赛材料目录")
    args = ap.parse_args()

    base = r"D:\pestguard\docs\参赛材料"
    outdir = os.path.join(base, "PDF")
    os.makedirs(outdir, exist_ok=True)

    targets = []
    if args.all:
        for fn in sorted(os.listdir(base)):
            if fn.endswith(".md"):
                targets.append((os.path.join(base, fn), os.path.join(outdir, fn[:-3] + ".pdf")))
    elif args.src:
        src = args.src
        dst = args.dst or os.path.join(outdir, os.path.basename(src)[:-3] + ".pdf")
        targets.append((src, dst))
    else:
        ap.print_help()
        return 1

    for src, dst in targets:
        if not os.path.exists(src):
            print(f"跳过（不存在）：{src}")
            continue
        try:
            size = convert(src, dst, s)
            print(f"OK  {os.path.basename(dst):<40} {size/1024:7.1f} KB")
        except Exception as e:
            print(f"ERR {os.path.basename(dst):<40} {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
