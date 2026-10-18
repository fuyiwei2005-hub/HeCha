"""LLM 汇总口径的回归测试。

这里锁的是一类极隐蔽的线上事故：视频结果先后被「展平」和「按事件」两种口径处理，
口径不匹配时 _summarize_video 会把每条检测当成一个空帧，输出
「视频共采样 203 帧，其中 0 帧检出目标」，模型据此回答「未发现任何害虫」——
界面上却画着 203 个框。这类错误不报错、不崩溃，只能靠断言挡住。
"""
import pytest

from app.services.llm import LLMAnalyzer


def _events():
    """2 个采样点，共 3 只蚜虫（第二帧里 2 只）。"""
    return [
        {"time_ms": 0, "detections": [
            {"class": "aphids", "class_cn": "蚜虫", "confidence": 0.9},
        ]},
        {"time_ms": 500, "detections": [
            {"class": "aphids", "class_cn": "蚜虫", "confidence": 0.8},
            {"class": "aphids", "class_cn": "蚜虫", "confidence": 0.7},
        ]},
    ]


def _flat():
    return [d for ev in _events() for d in ev["detections"]]


def test_video_events_summary_counts_frames_not_boxes():
    s = LLMAnalyzer._summarize_video(_events())
    assert "共采样 2 帧" in s
    assert "其中 2 帧检出目标" in s       # 不是 0 帧
    assert "蚜虫" in s
    assert "单帧最多 2 个" in s
    assert "时间跨度 0ms – 500ms" in s


def test_normalize_accepts_flat_list_for_video():
    """兼容旧调用：直接给展平列表也不能算出 0 帧检出。"""
    events, flat = LLMAnalyzer._normalize(_flat(), "video")
    assert len(flat) == 3
    s = LLMAnalyzer._summarize_video(events)
    assert "0 帧检出目标" not in s
    assert "蚜虫" in s


def test_normalize_keeps_events_intact():
    events, flat = LLMAnalyzer._normalize(_events(), "video")
    assert len(events) == 2
    assert len(flat) == 3


def test_image_normalize_returns_flat_only():
    preds = _flat()
    events, flat = LLMAnalyzer._normalize(preds, "image")
    assert events == []
    assert len(flat) == 3
    s = LLMAnalyzer._summarize(flat)
    # 图片必须按"本图检出 N 个目标"表述，而不是含糊的"出现 N 次"
    assert "本图检出 3 个目标" in s


# ── 图片/视频口径不能混 ────────────────────────────────────────────────
#
# 真实事故：系统提示里无条件写着"视频结果是按时间抽帧得到的，
# 同一只虫会在连续多帧被检出…在 N 个采样帧中被检出"。
# 于是**图片**分析也照抄：一张白菜照片（4 个目标）被写成
# "本视频按时间抽帧…多次检出"，一张柑橘照片（27 个目标）被写成
# "蚜虫在 18 个采样帧中被检出，说明其活动持续时间较长"。
# 用户看的是一张静态照片，却被告知帧数和持续时间 —— 事实性错误，
# 而且评委一眼就能看出来。

def test_image_prompt_forbids_frame_language():
    from app.services.llm import SYSTEM_PROMPT

    assert "单张静态照片" in SYSTEM_PROMPT, "图片提示没有说明这是照片"
    assert "绝对不要使用" in SYSTEM_PROMPT, "图片提示没有明确禁止帧类措辞"
    # 不能把视频口径当成默认写进图片提示
    assert "视频结果是按时间抽帧得到的" not in SYSTEM_PROMPT


def test_image_summary_has_no_time_wording():
    s = LLMAnalyzer._summarize([{"class_cn": "蚜虫", "confidence": 0.44}] * 27)
    for word in ("采样帧", "抽帧", "逐帧", "持续", "出现 27 次"):
        assert word not in s, f"图片汇总里出现时间性措辞 {word!r}：{s}"


def test_video_prompt_keeps_frame_language():
    from app.services.llm import SYSTEM_PROMPT_VIDEO

    assert "持续时间" in SYSTEM_PROMPT_VIDEO
    assert "采样帧数" in SYSTEM_PROMPT_VIDEO


def test_image_and_video_prompts_differ():
    from app.services.llm import SYSTEM_PROMPT, SYSTEM_PROMPT_VIDEO

    assert SYSTEM_PROMPT != SYSTEM_PROMPT_VIDEO


def test_empty_video_summary_is_explicit():
    s = LLMAnalyzer._summarize_video([])
    assert "未检出害虫" in s


class _FakeCompletions:
    def __init__(self, text):
        self._text = text

    async def create(self, **kwargs):  # noqa: ANN401 - 只记录入参
        _FakeCompletions.last_kwargs = kwargs
        return type(
            "R", (), {
                "choices": [type(
                    "C", (), {
                        "message": type("M", (), {"content": self._text})(),
                        "finish_reason": "stop",
                    }
                )()]
            }
        )()


class _FakeClient:
    def __init__(self, text):
        self.chat = type("Chat", (), {"completions": _FakeCompletions(text)})()


async def _run_analyze(monkeypatch, predictions, media_type, text="模拟回答" * 30):
    monkeypatch.setattr(LLMAnalyzer, "enabled", True)
    monkeypatch.setattr(LLMAnalyzer, "_get_client", lambda self: _FakeClient(text))
    return await LLMAnalyzer().analyze(predictions, media_type)


@pytest.mark.asyncio
async def test_analyze_image_does_not_crash(monkeypatch):
    """曾经因为只在 video 分支里定义了 summary，图片分支直接 UnboundLocalError，
    整个 /detections/image 接口 500——界面表现就是「图片识别不出结果」。"""
    out = await _run_analyze(monkeypatch, _flat(), "image")
    assert out is not None
    body = _FakeCompletions.last_kwargs["messages"][1]["content"]
    assert "静态照片" in body
    assert "本图检出 3 个目标" in body
    # 给模型看的正文里不能再有视频口径
    assert "抽帧" not in body
    # 系统提示也必须是图片那套
    sys_msg = _FakeCompletions.last_kwargs["messages"][0]["content"]
    assert "单张静态照片" in sys_msg
    assert "视频结果是按时间抽帧得到的" not in sys_msg


@pytest.mark.asyncio
async def test_analyze_video_uses_frame_wording(monkeypatch):
    out = await _run_analyze(monkeypatch, _events(), "video")
    assert out is not None
    body = _FakeCompletions.last_kwargs["messages"][1]["content"]
    assert "视频逐帧检测结果" in body
    assert "其中 2 帧检出目标" in body
    assert "0 帧检出目标" not in body


@pytest.mark.asyncio
async def test_analyze_video_tolerates_flat_input(monkeypatch):
    """即便调用方传错（展平列表），也不能把「有检出」说成「未检出」。"""
    await _run_analyze(monkeypatch, _flat(), "video")
    body = _FakeCompletions.last_kwargs["messages"][1]["content"]
    assert "0 帧检出目标" not in body
    assert "蚜虫" in body
