"""把 docs/参赛材料 下的 Markdown 转成 PDF（官方要求 PDF 格式提交）。

用法：
    python tools/md2pdf.py                 # 转全部
    python tools/md2pdf.py 作品简介.md      # 只转指定文件

说明：只支持**纯文本段落**型 Markdown（标题 + 加粗 + 段落）。
带复杂表格的文档（如软件设计文档）建议用 Typora / VS Code Markdown 插件
导出 PDF，表格排版更可靠。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT.parent / "docs" / "参赛材料"
OUT_DIR = SRC_DIR / "PDF"
FONT_DIR = Path("C:/Windows/Fonts")


class Doc(FPDF):
    def header(self) -> None:
        pass

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("cn", size=9)
        self.set_text_color(140, 140, 140)
        self.cell(0, 10, f"{self.page_no()}", align="C")


def pick_font() -> tuple[Path, Path]:
    """返回 (常规, 粗体) 字体路径。"""
    reg = FONT_DIR / "simhei.ttf"
    bold = FONT_DIR / "simhei.ttf"  # 黑体本身较粗，粗体复用
    if not reg.is_file():
        raise SystemExit(f"找不到中文字体：{reg}")
    return reg, bold


def convert(md_path: Path) -> Path:
    text = md_path.read_text(encoding="utf-8")
    reg, bold = pick_font()

    pdf = Doc()
    pdf.add_font("cn", "", str(reg))
    pdf.add_font("cn", "B", str(bold))
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            pdf.ln(4)
            continue

        if line.startswith("# "):
            pdf.set_font("cn", "B", 17)
            pdf.multi_cell(0, 11, line[2:].strip(), align="C")
            pdf.ln(6)
            continue
        if line.startswith("## "):
            pdf.set_font("cn", "B", 13)
            pdf.multi_cell(0, 9, line[3:].strip())
            pdf.ln(3)
            continue
        if line.startswith("### "):
            pdf.set_font("cn", "B", 11.5)
            pdf.multi_cell(0, 8, line[4:].strip())
            pdf.ln(2)
            continue

        pdf.set_font("cn", "", 11)
        # 去掉 ** 粗体标记（PDF 里统一按正文排，避免行内样式错位）
        plain = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        plain = plain.replace("`", "")
        pdf.multi_cell(0, 7.5, plain)
        pdf.ln(1.5)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / (md_path.stem + ".pdf")
    pdf.output(str(out))
    return out


def main() -> int:
    targets = sys.argv[1:]
    if targets:
        files = [SRC_DIR / t for t in targets]
    else:
        # 默认只转纯文本型文档，表格型的不在这里
        files = [SRC_DIR / "作品简介.md", SRC_DIR / "AI使用声明.md"]

    ok = 0
    for f in files:
        if not f.is_file():
            print(f"[跳过] 不存在：{f}")
            continue
        out = convert(f)
        size = out.stat().st_size // 1024
        print(f"[完成] {f.name} -> {out.name} ({size} KB)")
        ok += 1
    print(f"\n输出目录：{OUT_DIR}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
