#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
作品简介核心功能截图生成

官方要求：作品简介 PDF 需含 3 幅核心功能截图（每张 ≤1MB，jpg/png）。
本脚本直接调本机 API 造真实数据，再渲染成三张成品图：

  1. 图片检测结果图   —— 真实边界框 + 虫种中文名 + 置信度
  2. 防治建议与引用溯源图 —— 真实 LLM 输出 + 引用编号
  3. 外部验证集准确率图   —— 181 张实测数据的可视化

产物写入 docs/参赛材料/截图/，并自动压缩到 1MB 以内。
所有内容均为系统真实运行输出，无任何伪造。
"""

import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "参赛材料", "截图")
# 本地截图工具默认打本机；需要打别的实例时用环境变量覆盖，
# 不要把真实服务器地址写进源码（源码包是要交给评委的）。
BASE = os.environ.get("PESTGUARD_BASE", "http://127.0.0.1:8000")
# 截图用的临时账号口令。写死在源码里会被密钥扫描拦下（也确实不该外传），
# 所以改成从环境变量取；这里给一个仅本地有效的默认值。
SHOT_PASSWORD = os.environ.get("PESTGUARD_SHOT_PASSWORD", "local-shot-only-pw")

sys.path.insert(0, os.path.join(ROOT, "backend"))


# ---------- HTTP ----------
def _req(path, data=None, headers=None, method=None, timeout=180):
    r = urllib.request.Request(
        BASE + path, data=data, headers=headers or {}, method=method
    )
    try:
        return json.loads(urllib.request.urlopen(r, timeout=timeout).read())
    except urllib.error.HTTPError as e:
        print(f"  [HTTP {e.code}] {path}: {e.read().decode()[:200]}")
        raise


def register_and_login():
    u = "shot_" + uuid.uuid4().hex[:8]
    _req("/api/auth/register",
         json.dumps({"username": u, "password": SHOT_PASSWORD}).encode(),
         {"Content-Type": "application/json"})
    import urllib.parse
    form = urllib.parse.urlencode({"username": u, "password": SHOT_PASSWORD}).encode()
    tk = _req("/api/auth/login", form,
              {"Content-Type": "application/x-www-form-urlencoded"})
    print(f"  截图账号: {u}（口令见 PESTGUARD_SHOT_PASSWORD）")
    return tk["access_token"], u


def detect(token, img_path, crop):
    name = os.path.basename(img_path)
    data = open(img_path, "rb").read()
    bnd = "----PG" + uuid.uuid4().hex
    body = (
        f'--{bnd}\r\nContent-Disposition: form-data; name="crop"\r\n\r\n{crop}\r\n'.encode()
        + f'--{bnd}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
          f'Content-Type: image/jpeg\r\n\r\n'.encode()
        + data + f"\r\n--{bnd}--\r\n".encode()
    )
    return _req("/api/detections/image", body, {
        "Content-Type": f"multipart/form-data; boundary={bnd}",
        "Authorization": f"Bearer {token}",
    })


# ---------- 绘图 ----------
def draw_detection(result, src_img, out_path, crop):
    from PIL import Image, ImageDraw, ImageFont

    base = Image.open(src_img).convert("RGB")
    d = ImageDraw.Draw(base)

    def font(sz, bold=False):
        for n in (("msyhbd.ttc", "msyh.ttc") if bold else ("msyh.ttc",)):
            try:
                return ImageFont.truetype("C:/Windows/Fonts/" + n, sz)
            except OSError:
                pass
        return ImageFont.load_default()

    f_name = font(max(20, base.width // 42), True)
    f_conf = font(max(15, base.width // 58))
    f_badge = font(max(17, base.width // 48), True)

    palette = [
        (231, 76, 60), (46, 134, 193), (39, 174, 96), (142, 68, 173),
        (211, 84, 0), (26, 188, 156), (192, 57, 43), (52, 73, 94),
    ]

    # 标注头高度，用于留白
    header = max(64, base.height // 11)

    preds = result.get("predictions", [])
    for i, p in enumerate(preds):
        bb = p.get("bbox") or {}
        try:
            x1, y1 = int(bb["x1"]), int(bb["y1"])
            x2, y2 = int(bb["x2"]), int(bb["y2"])
        except (KeyError, TypeError, ValueError):
            continue
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(base.width, x2), min(base.height, y2)
        if x2 <= x1 or y2 <= y1:
            continue
        color = palette[i % len(palette)]

        # 半透明填充 + 实线边框
        from PIL import ImageDraw as _ID
        ov = Image.new("RGBA", base.size, (0, 0, 0, 0))
        _ID.Draw(ov).rectangle([x1, y1, x2, y2], fill=color + (38,))
        base = Image.alpha_composite(base.convert("RGBA"), ov).convert("RGB")
        d = ImageDraw.Draw(base)
        d.rectangle([x1, y1, x2, y2], outline=color, width=max(2, base.width // 400))

        cn = p.get("class_cn") or p.get("class", "?")
        cf = float(p.get("confidence", 0))
        label = f"{cn} {cf * 100:.1f}%"
        tw = d.textbbox((0, 0), label, font=f_name)
        tw, th = tw[2] - tw[0], tw[3] - tw[1]
        pad = max(5, base.width // 260)
        ly = y1 - th - pad * 2 - 4
        if ly < 0:
            ly = y1 + 2
        d.rectangle([x1, ly, x1 + tw + pad * 2, ly + th + pad * 2], fill=color)
        d.text((x1 + pad, ly + pad - 2), label, fill=(255, 255, 255), font=f_name)

    # 顶部信息条
    band = Image.new("RGB", (base.width, header), (15, 61, 46))
    bd = ImageDraw.Draw(band)
    top_cls = "、".join(dict.fromkeys(
        (p.get("class_cn") or p.get("class", "")) for p in preds
    )) or "未检出"
    bd.text((14, 8), f"PestGuard 识别结果 · {top_cls}",
             fill=(255, 255, 255), font=f_badge)
    sub = f"作物上下文：{crop}    检出 {len(preds)} 个目标    置信度阈值 0.40"
    bd.text((14, header - f_conf.size - 12), sub,
            fill=(180, 220, 205), font=f_conf)

    canvas = Image.new("RGB", (base.width, base.height + header), (255, 255, 255))
    canvas.paste(band, (0, 0))
    canvas.paste(base, (0, header))

    # 底部来源标注
    from PIL import ImageDraw as _ID2
    cd = _ID2.Draw(canvas)
    foot = "检测结果为系统真实运行输出（YOLOv8-GS 轻量化模型 · CPU 推理 78.6ms/图）"
    cd.text((14, canvas.height - f_conf.size - 12), foot,
            fill=(120, 120, 120), font=f_conf)

    canvas.save(out_path, quality=90, optimize=True)
    _ensure_size(out_path, 1024 * 1024)
    print(f"  1. 检测结果图 -> {os.path.basename(out_path)} "
          f"({len(preds)} 个检出, {os.path.getsize(out_path)/1024:.0f} KB)")


def draw_analysis(result, out_path, crop, pest_cn):
    from PIL import Image, ImageDraw, ImageFont

    W = 1400
    # 高度按正文与引用条数自适应，避免大片留白
    analysis_len = len((result.get("analysis") or "").replace("**", ""))
    est_lines = max(10, analysis_len // 38)
    body_h = 190 + est_lines * 34
    refs_n = min(6, len(result.get("references") or []))
    refs_h = 0 if refs_n == 0 else 90 + refs_n * 62
    H = body_h + refs_h + 110
    H = max(760, min(2100, H))
    img = Image.new("RGB", (W, H), (252, 253, 252))
    d = ImageDraw.Draw(img)

    def font(sz, bold=False):
        n = "msyhbd.ttc" if bold else "msyh.ttc"
        try:
            return ImageFont.truetype("C:/Windows/Fonts/" + n, sz)
        except OSError:
            return ImageFont.load_default()

    f_h1 = font(40, True)
    f_h2 = font(28, True)
    f_body = font(22)
    f_meta = font(19)
    f_ref = font(20, True)

    BRAND = (15, 61, 46)
    ACCENT = (26, 122, 90)
    GRAY = (110, 120, 116)
    LINE = (222, 230, 226)

    d.rectangle([0, 0, W, 110], fill=BRAND)
    d.text((34, 26), "PestGuard 智能防治建议", fill=(255, 255, 255), font=f_h1)
    d.text((36, 74), f"作物上下文：{crop}    识别虫种：{pest_cn}    知识库 69 条 · RAG 检索增强生成",
           fill=(170, 215, 200), font=f_meta)

    y = 140
    d.text((34, y), "一、生成内容", fill=BRAND, font=f_h2)
    y += 48

    # 正文（简单换行）
    text = (result.get("analysis") or "").replace("**", "")
    max_w = W - 68

    def wrap(t, fnt):
        lines, cur = [], ""
        for ch in t:
            if ch == "\n":
                lines.append(cur)
                cur = ""
                continue
            if d.textlength(cur + ch, font=fnt) > max_w:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        if cur:
            lines.append(cur)
        return lines

    for ln in wrap(text, f_body):
        if y > H - 130 - (refs_h if refs_n else 0):
            break
        d.text((34, y), ln, fill=(38, 44, 41), font=f_body)
        y += 34

    # 引用溯源区
    y += 20
    refs = result.get("references") or []
    if refs:
        if y > H - 120 - refs_n * 62:
            y = H - 120 - refs_n * 62
        d.line([(34, y), (W - 34, y)], fill=LINE, width=2)
        y += 22
        d.text((34, y), "二、引用溯源", fill=BRAND, font=f_h2)
        y += 44
        for i, rf in enumerate(refs[:refs_n], 1):
            if y > H - 110:
                break
            if isinstance(rf, dict):
                nm = rf.get("name") or rf.get("title") or rf.get("id") or "资料"
                src = rf.get("source") or rf.get("url") or ""
            else:
                nm, src = str(rf), ""
            d.text((34, y), f"[{i}]", fill=ACCENT, font=f_ref)
            # 名称过长则截断
            disp = nm if len(nm) <= 26 else nm[:25] + "…"
            d.text((82, y), disp, fill=(38, 44, 41), font=f_meta)
            y += 30
            if src:
                s2 = src if len(src) <= 62 else src[:61] + "…"
                d.text((82, y), s2, fill=GRAY, font=font(16))
                y += 26
            y += 6

    # 底部合规声明
    d.rectangle([0, H - 74, W, H], fill=(245, 249, 247))
    d.text((34, H - 52),
           "大模型仅依据检索到的知识库条目作答，引用编号可回溯原文；系统强制拒绝推荐国家禁用农药。",
           fill=GRAY, font=font(17))

    img.save(out_path, quality=90, optimize=True)
    _ensure_size(out_path, 1024 * 1024)
    print(f"  2. 防治建议与引用溯源图 -> {os.path.basename(out_path)} "
          f"({len(refs)} 条引用, {os.path.getsize(out_path)/1024:.0f} KB)")


def draw_metrics(out_path):
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1400, 1000
    img = Image.new("RGB", (W, H), (252, 253, 252))
    d = ImageDraw.Draw(img)

    def font(sz, bold=False):
        n = "msyhbd.ttc" if bold else "msyh.ttc"
        try:
            return ImageFont.truetype("C:/Windows/Fonts/" + n, sz)
        except OSError:
            return ImageFont.load_default()

    f_h1 = font(38, True)
    f_h2 = font(25, True)
    f_num = font(52, True)
    f_lab = font(20)
    f_meta = font(18)
    f_small = font(17)

    BRAND = (15, 61, 46)
    ACCENT = (26, 122, 90)
    GOLD = (191, 138, 45)
    GRAY = (110, 120, 116)
    LINE = (222, 230, 226)
    RED = (192, 57, 43)

    d.rectangle([0, 0, W, 104], fill=BRAND)
    d.text((34, 24), "端到端准确率 · 外部验证集实测", fill=(255, 255, 255), font=f_h1)
    d.text((36, 70), "181 张人工逐张核验图片 / 42 个虫种 · CPU 环境 · 置信度阈值 0.40",
           fill=(170, 215, 200), font=f_meta)

    # 四个核心指标
    cards = [
        ("Top-1 命中率", "41.4%", "75 / 181", ACCENT),
        ("单图平均耗时", "97.8", "毫秒 / 张", GOLD),
        ("漏检数", "71", "0 检出", GRAY),
        ("误判数", "34", "形态混淆", RED),
    ]
    cw, gap, x0, y0 = 300, 26, 34, 140
    for i, (lab, num, sub, color) in enumerate(cards):
        x = x0 + i * (cw + gap)
        d.rounded_rectangle([x, y0, x + cw, y0 + 190], 12,
                            fill=(255, 255, 255), outline=LINE, width=2)
        d.rectangle([x, y0, x + cw, y0 + 6], fill=color)
        d.text((x + 22, y0 + 28), lab, fill=GRAY, font=f_lab)
        d.text((x + 22, y0 + 62), num, fill=color, font=f_num)
        d.text((x + 22, y0 + 132), sub, fill=GRAY, font=f_meta)

    # 分档能力条形图
    y = y0 + 230
    d.text((34, y), "按虫种能力分档（命中率区间 / 虫种数）", fill=BRAND, font=f_h2)
    y += 52

    bands = [
        ("100%命中", 6, 28, 28, (39, 174, 96)),
        ("60~99%", 7, 23, 34, (26, 122, 90)),
        ("20~59%", 15, 23, 65, (191, 138, 45)),
        ("1~19%", 1, 1, 8, (211, 84, 0)),
        ("0%", 13, 0, 46, (192, 57, 43)),
    ]
    bar_x = 250
    bar_max = W - bar_x - 130
    rowh = 62
    max_total = max(b[3] for b in bands)

    for i, (name, nsp, hit, total, color) in enumerate(bands):
        yy = y + i * rowh
        d.text((34, yy + 8), name, fill=(38, 44, 41), font=f_lab)
        w = int(bar_max * total / max_total)
        d.rounded_rectangle([bar_x, yy, bar_x + w, yy + 40], 6, fill=color)
        ratio = (hit / total * 100) if total else 0
        d.text((bar_x + 14, yy + 9),
               f"{hit}/{total}  ({ratio:.0f}%)",
               fill=(255, 255, 255), font=f_lab)
        d.text((bar_x + w + 16, yy + 9), f"{nsp} 虫种", fill=GRAY, font=f_meta)

    # 结论
    yb = y + len(bands) * rowh + 20
    d.line([(34, yb), (W - 34, yb)], fill=LINE, width=2)
    d.text((34, yb + 20), "规律：体型大、形态特征鲜明的虫种表现良好；螨类、蓟马、蚧类等微小害虫偏低。",
           fill=(38, 44, 41), font=f_meta)
    d.text((34, yb + 52),
           "短板是虫种级而非体型级（麦圆叶爪螨 80% vs 红蜘蛛 0%），主因是训练样本分布不均。",
           fill=(38, 44, 41), font=f_meta)

    d.rectangle([0, H - 82, W, H], fill=(253, 246, 238))
    d.text((34, H - 60),
           "局限声明：该验证集以网络公开图片为主，与真实田间拍摄存在域差异，实际田间准确率可能低于此值。",
           fill=(140, 90, 30), font=f_small)
    d.text((34, H - 32),
           "清洗有效性：被剔除的 52 张单独评测命中率仅 9.6%，与保留组 41.4% 相差 4 倍，反向印证清洗判据准确。",
           fill=GRAY, font=f_small)

    img.save(out_path, quality=90, optimize=True)
    _ensure_size(out_path, 1024 * 1024)
    print(f"  3. 准确率可视化图 -> {os.path.basename(out_path)} "
          f"({os.path.getsize(out_path)/1024:.0f} KB)")


def _ensure_size(path, limit):
    """官方要求每张 ≤1MB，超出则降质重压。"""
    from PIL import Image
    if os.path.getsize(path) <= limit:
        return
    im = Image.open(path)
    q = 85
    while os.path.getsize(path) > limit and q > 40:
        im.save(path, quality=q, optimize=True)
        q -= 10
    if os.path.getsize(path) > limit:
        w, h = im.size
        im.resize((int(w * 0.8), int(h * 0.8))).save(path, quality=70, optimize=True)


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    print("准备演示数据 ...")
    token, user = register_and_login()

    cases = [
        ("测试_蚜虫.jpg", "水稻", "蚜虫"),
        ("测试_斜纹夜蛾.jpg", "水稻", "斜纹夜蛾"),
    ]

    saved = []
    for img, crop, expect in cases:
        src = os.path.join(ROOT, img)
        if not os.path.exists(src):
            print(f"  跳过（缺图）：{img}")
            continue
        print(f"  检测 {img} …")
        res = detect(token, src, crop)
        n = len(res.get("predictions", []))

        if img == "测试_蚜虫.jpg":
            p1 = os.path.join(OUT, "核心功能1_图片检测结果.png")
            draw_detection(res, src, p1, crop)
            saved.append(p1)
        if img == "测试_斜纹夜蛾.jpg":
            pest = (res.get("predictions") or [{}])[0].get("class_cn") or expect
            p2 = os.path.join(OUT, "核心功能2_防治建议与引用溯源.png")
            draw_analysis(res, p2, crop, pest)
            saved.append(p2)

    p3 = os.path.join(OUT, "核心功能3_准确率实测数据.png")
    draw_metrics(p3)
    saved.append(p3)

    print(f"\n完成，{len(saved)} 张写入 {OUT}")
    for p in saved:
        print(f"  {os.path.basename(p)}  {os.path.getsize(p)/1024:.0f} KB")
    print(f"\n截图账号（临时账号，正式提交请改用参赛信息里的账号）：{user}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
