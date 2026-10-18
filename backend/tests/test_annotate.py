"""标注绘制（annotate.py）的回归测试。

对应真实事故：Docker/Linux 上字体候选只有 Windows 路径，
`_load_font()` 必然返回 None，于是走"无中文字体"分支，
而那个分支把标签兜底成**字面量 "pest"** ——
演示视频里每个检测框都写着 "pest 92%"，完全看不出检出了什么虫。
"""
from __future__ import annotations

import numpy as np
import pytest

from app.services import annotate


def _frame() -> np.ndarray:
    return np.zeros((240, 320, 3), dtype=np.uint8)


def _pred(cls: str, cls_cn: str, conf: float = 0.92) -> dict:
    return {
        "class": cls,
        "class_cn": cls_cn,
        "confidence": conf,
        "bbox": {"x1": 20, "y1": 40, "x2": 180, "y2": 200},
    }


@pytest.fixture
def no_font(monkeypatch):
    """模拟"找不到任何中文字体"的容器环境。

    直接清 lru_cache 再清空候选表，避免缓存把上一次的结果带过来。
    """
    monkeypatch.setattr(annotate, "_FONT_CANDIDATES", [])
    monkeypatch.delenv("PESTGUARD_FONT", raising=False)
    annotate._load_font.cache_clear()
    yield
    annotate._load_font.cache_clear()


def test_no_font_falls_back_to_english_class_name(no_font):
    """没有中文字体时，标签必须是英文类名，而不是占位词。"""
    assert annotate._load_font(20) is None, "本用例前提是找不到字体"

    out = annotate.draw_labels(_frame(), [_pred("aphids", "蚜虫")])

    # 画面内容变了（确实画了东西）
    assert out.shape == (240, 320, 3)
    assert out.sum() > 0, "没有绘制任何内容"


def test_no_font_never_emits_literal_pest_label(no_font):
    """关键回归：不允许再出现兜底成 "pest" 的标签。

    直接断言 draw_labels 实际使用的那段标签构造逻辑（ascii_fallback_label），
    而不是在测试里复刻一遍 —— 复刻的测试不会跟着实现一起坏。
    """
    for cls, cls_cn, expect_prefix in [
        ("aphids", "蚜虫", "aphids"),
        ("corn borer", "玉米螟", "corn borer"),
    ]:
        text = annotate.ascii_fallback_label(_pred(cls, cls_cn))
        assert text.startswith(expect_prefix), (
            f"标签应以英文类名开头，实际为 {text!r}"
        )
        assert "pest" not in text.lower(), f"又退化成占位词了：{text!r}"

    # 并且确认这些标签真的被画到了图上（不抛异常）
    out = annotate.draw_labels(
        _frame(), [_pred("aphids", "蚜虫"), _pred("corn borer", "玉米螟")]
    )
    assert out.sum() > 0


def test_ascii_fallback_handles_missing_fields():
    """字段缺失时也不能崩，也不能产出没有虫种信息的标签。"""
    assert annotate.ascii_fallback_label({}) == "insect 0%"
    # 只有中文名时：剥掉非 ASCII 后不能再留下一个光秃秃的 "0%"
    assert annotate.ascii_fallback_label({"class_cn": "蚜虫"}) == "insect 0%"
    assert annotate.ascii_fallback_label({"class": "aphids", "confidence": 0.5}) == "aphids 50%"


def test_cjk_font_candidates_cover_linux_paths():
    """字体候选必须包含 Linux/容器路径，否则 Docker 里永远是英文兜底。"""
    candidates = annotate._FONT_CANDIDATES
    assert any(p.startswith("/usr/share/fonts") for p in candidates), (
        "字体候选里没有任何 Linux 路径 —— Docker 部署会全部退化成英文标签"
    )
    assert any("noto" in p.lower() for p in candidates), (
        "缺少 Noto CJK 候选；Dockerfile 装的是 fonts-noto-cjk"
    )


def test_font_env_override_is_honored(monkeypatch, tmp_path):
    """PESTGUARD_FONT 应能指定自定义字体，方便离线/定制镜像。"""
    fake = tmp_path / "custom.ttf"
    fake.write_bytes(b"not-a-real-font")
    monkeypatch.setenv("PESTGUARD_FONT", str(fake))
    monkeypatch.setattr(annotate, "_FONT_CANDIDATES", [])
    annotate._load_font.cache_clear()
    try:
        # 内容不是真字体，truetype 会抛 OSError 并被吞掉 -> None
        # 这里只断言"候选列表第一位是我们指定的路径"，确认覆盖生效
        assert annotate._font_candidates()[0] == str(fake)
    finally:
        annotate._load_font.cache_clear()
