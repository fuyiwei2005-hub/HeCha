"""在 OpenCV 画面上绘制中文检测标签。

cv2.putText 只支持 ASCII（HERSHEY 字体集），直接画「蚜虫」会渲染成 ???。
这里用 PIL 绘制标签文本，再转回 BGR ndarray 交给 cv2 使用。
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# 中文字体候选：**跨平台**。
# 之前只有 Windows 路径，于是 Docker/Linux 上必然找不到字体，
# 走 ASCII 兜底分支，每个检测框都显示成字面量 "pest 92%"。
# 容器里由 backend/Dockerfile 安装 fonts-noto-cjk；下面同时覆盖
# 常见的 Debian/Ubuntu 与 Alpine 字体位置，以及 WQY 等替代品。
_FONT_CANDIDATES = [
    # ---- Linux（Docker 运行时）----
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    # ---- Windows（本地开发）----
    r"C:\Windows\Fonts\msyh.ttc",      # 微软雅黑
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",    # 黑体
    r"C:\Windows\Fonts\simsun.ttc",    # 宋体
    # ---- macOS ----
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
]

BOX_COLOR = (90, 210, 40)      # BGR，与前端主题绿一致
TEXT_COLOR = (255, 255, 255)
FILL_COLOR = (135, 120, 4)     # 深绿底（BGR），给文字做背景条


def _font_candidates() -> list[str]:
    """字体候选；允许用环境变量追加自定义字体（离线/自定义镜像场景）。"""
    extra = os.environ.get("PESTGUARD_FONT", "").strip()
    return ([extra] if extra else []) + _FONT_CANDIDATES


@lru_cache(maxsize=4)
def _load_font(size: int) -> ImageFont.FreeTypeFont | None:
    for path in _font_candidates():
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    # 只在第一次（lru_cache 未命中）告警一次，避免逐帧刷屏
    logger.warning(
        "未找到任何中文字体，检测标签将退化为英文类名。"
        "容器部署请确认镜像装了 fonts-noto-cjk；"
        "或用 PESTGUARD_FONT 指定字体文件路径。"
    )
    return None


def ascii_fallback_label(pred: dict) -> str:
    """无中文字体时使用的标签文本。

    抽成独立函数是为了让它可被测试直接断言 —— 之前这段逻辑内联在
    draw_labels 里，兜底值是字面量 "pest"，结果 Docker 上每个框都写
    "pest 92%"，而且没有任何测试能发现。
    """
    conf = float(pred.get("confidence") or 0.0)
    # 中文标签在纯 ASCII 字体下会被 encode("ascii","ignore") 整段剥空，
    # 所以优先用英文类名。
    english = str(pred.get("class") or "").strip()
    ascii_label = english.encode("ascii", "ignore").decode().strip()
    if not ascii_label:
        # 英文类名也拿不到（或本身含非 ASCII）：退到中文名再剥一次，
        # 仍然为空就用中性词。注意不能只在"整体为空"时才兜底 ——
        # "蚜虫 0%" 剥完剩 "0%"，非空但完全没有虫种信息。
        ascii_label = str(pred.get("class_cn") or "").encode(
            "ascii", "ignore").decode().strip()
    if not ascii_label:
        ascii_label = "insect"
    return f"{ascii_label} {conf:.0%}"


def draw_labels(frame: np.ndarray, predictions: list[dict]) -> np.ndarray:
    """在 frame 上画框和中文标签（含置信度），返回新图。"""
    if not predictions:
        return frame

    h, w = frame.shape[:2]
    # 字号随画面高度自适应：1080p 约 22px，480p 约 14px
    font_size = max(12, min(28, round(h / 40)))
    font = _load_font(font_size)

    # 没有中文字体时走纯 cv2 分支（英文标签），不需要任何色彩空间转换
    if font is None:
        for pred in predictions:
            box = pred.get("bbox") or {}
            try:
                x1, y1 = int(box["x1"]), int(box["y1"])
                x2, y2 = int(box["x2"]), int(box["y2"])
            except (KeyError, TypeError, ValueError):
                continue
            conf = float(pred.get("confidence") or 0.0)
            text = ascii_fallback_label(pred)
            cv2.rectangle(frame, (x1, y1), (x2, y2), BOX_COLOR, 2)
            cv2.putText(frame, text,
                        (x1, max(12, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX,
                        max(0.4, font_size / 32), BOX_COLOR, 2)
        return frame

    # 两遍绘制：框和背景条是矩形，cv2 在 BGR 上直接画，零转换开销；
    # 只有中文文字必须交给 PIL，所以整帧**只做一次** BGR→RGB→BGR 往返。
    # （原实现在每个框里各往返一次，20 个框就是 20 次全帧拷贝 —— 1080p 下
    #   单次拷贝约 6MB，多目标帧的内存与 CPU 峰值都被白白放大了 20 倍。）
    texts: list[tuple[str, int, int]] = []
    for pred in predictions:
        box = pred.get("bbox") or {}
        try:
            x1, y1 = int(box["x1"]), int(box["y1"])
            x2, y2 = int(box["x2"]), int(box["y2"])
        except (KeyError, TypeError, ValueError):
            continue
        # 中文优先，缺失时回退英文类名
        label = str(pred.get("class_cn") or pred.get("class") or "unknown")
        conf = float(pred.get("confidence") or 0.0)
        text = f"{label} {conf:.0%}"

        cv2.rectangle(frame, (x1, y1), (x2, y2), BOX_COLOR, 2)

        # 背景条贴在框的上方外侧，避免遮住虫体
        left, top, right, bottom = font.getbbox(text)
        tw, th = right - left, bottom - top
        pad = 4
        ty = y1 - th - 2 * pad
        if ty < 0:                      # 贴到画面顶端时改贴框内
            ty = y1 + 2
        tx = min(x1, w - tw - 2 * pad)
        tx = max(0, tx)
        cv2.rectangle(frame, (tx, ty), (tx + tw + 2 * pad, ty + th + 2 * pad), FILL_COLOR, -1)
        texts.append((text, tx + pad, ty + pad))

    if not texts:
        return frame

    pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    for text, tx, ty in texts:
        draw.text((tx, ty), text, font=font, fill=TEXT_COLOR)
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
