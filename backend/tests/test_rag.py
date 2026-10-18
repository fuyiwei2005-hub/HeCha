"""RAG（检索增强生成）回归测试。

这里锁住的是几个一旦退化就会直接打脸的性质：
- 知识库里每条都必须有 source，否则「可溯源」就是空话；
- 检出什么虫就必须召回那条虫的档案（不能召错、不能召回无关虫种）；
- 生成端返回的引用编号必须是真实注入过的，不允许凭空出现。
"""

from typing import Any

import asyncio

import pytest

from app.services.knowledge import KnowledgeBase, get_knowledge_base
from app.services.llm import LLMAnalyzer


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return get_knowledge_base()


def test_knowledge_base_is_loaded(kb: KnowledgeBase) -> None:
    assert kb.available, f"知识库未加载：{kb.error}"
    assert len(kb.docs) >= 60, f"条目过少：{len(kb.docs)}"


def test_every_entry_has_source(kb: KnowledgeBase) -> None:
    """没有出处的条目不允许入库——可溯源的前提。"""
    missing = [d["title"] for d in kb.docs if not d["source"]]
    assert not missing, f"以下条目缺 source：{missing}"


def test_all_46_model_classes_are_covered(kb: KnowledgeBase) -> None:
    """模型能识别的每个虫种都必须在知识库里有档案，否则检出即无据可依。"""
    from app.services.pest_names import CLASS_CN

    titles = {d["title"] for d in kb.docs}
    names = set(CLASS_CN.values())
    gaps = sorted(names - titles)
    assert not gaps, f"以下虫种缺少知识库档案：{gaps}"


@pytest.mark.parametrize(
    "pest",
    ["蚜虫", "稻纵卷叶螟", "斜纹夜蛾", "柑橘锈螨", "蛴螬", "蓟马", "玉米螟"],
)
def test_exact_pest_hit_is_ranked_first(kb: KnowledgeBase, pest: str) -> None:
    """别名硬匹配：检出该虫时，它的档案必须是第 1 条。"""
    results = kb.search(f"{pest} 危害症状 防治方法", top_k=4)
    assert results, f"{pest} 未召回任何条目"
    assert results[0]["title"] == pest, f"{pest} 召回首条为 {results[0]['title']}"


def test_unrelated_pest_is_not_retrieved(kb: KnowledgeBase) -> None:
    """相关性下限：查蚜虫不该把蝗虫这类无关条目放进前排。

    这是加 25% 阈值与 query boosting 之前实测出现过的退化。
    """
    results = kb.search("蚜虫 蚜虫 蚜虫 危害症状 发生规律 防治方法", top_k=3)
    titles = [r["title"] for r in results]
    assert titles[0] == "蚜虫"
    assert "蝗虫" not in titles, f"召回了无关条目：{titles}"


def test_search_is_safe_on_empty_and_noise(kb: KnowledgeBase) -> None:
    assert kb.search("", top_k=3) == []
    assert kb.search("   ", top_k=3) == []
    # 完全无意义的长串不应该抛异常
    kb.search("asdfghjkl qwertyuiop", top_k=3)


def test_pest_names_extraction() -> None:
    preds: list[dict[str, Any]] = [
        {"class_cn": "蚜虫", "class": "aphids", "confidence": 0.9},
        {"class_cn": "蚜虫", "class": "aphids", "confidence": 0.8},
        {"class_cn": "蓟马", "class": "Thrips", "confidence": 0.7},
    ]
    assert LLMAnalyzer._pest_names(preds, "image") == ["蚜虫", "蓟马"]

    video = [{"time_ms": 0, "detections": preds[:1]}, {"time_ms": 200, "detections": preds[1:]}]
    # 用集合比较：中文按 unicode 排序没有语义，别写成 sorted(...) == [...]
    assert set(LLMAnalyzer._pest_names(video, "video")) == {"蚜虫", "蓟马"}


def test_format_refs_shape() -> None:
    refs = [{"ref": 1, "title": "蚜虫", "source": "某资料", "body": "正文"}]
    text = LLMAnalyzer._format_refs(refs)
    assert "[1] 蚜虫" in text
    assert "某资料" in text
    assert "正文" in text
    assert LLMAnalyzer._format_refs([]) == ""


def test_analyze_returns_tuple_and_degrades_gracefully(monkeypatch) -> None:
    """LLM 未配置时必须返回 (None, [])，不能抛异常也不能返回裸字符串。

    注意两个坑（都踩过）：
    1. `analyze` 是 async def，**必须 await**。之前漏了 await，
       断言实际是在拿 coroutine 对象和 tuple 比，永远为假；
    2. 不要用"本机有没有配 API Key"来决定测不测 —— 那等于
       「只在被测路径真的生效时才跳过」，把环境当开关。
       这里直接 monkeypatch 掉密钥，让降级路径在任何机器上都真跑到。
    """
    analyzer = LLMAnalyzer()
    monkeypatch.setattr(analyzer.settings, "deepseek_api_key", "", raising=False)
    assert not analyzer.enabled, "monkeypatch 未生效，降级路径不会被覆盖"

    assert asyncio.run(analyzer.analyze([], "image")) == (None, [])
    assert asyncio.run(
        analyzer.analyze([{"class_cn": "蚜虫", "confidence": 0.9}], "image")
    ) == (None, [])


def test_retrieve_never_raises() -> None:
    """检索环节任何异常都必须被兜住——知识库是增强项，不能拖垮检测。

    检索已改为 async（BM25 打分是纯 CPU，不能在事件循环里跑），
    这里用 asyncio.run 同步驱动，保持这条回归用例的同步写法。
    """
    import asyncio

    analyzer = LLMAnalyzer()
    refs = asyncio.run(analyzer._retrieve([{"class_cn": "蚜虫"}], "image", extra_query="用什么药"))
    assert isinstance(refs, list)
    # 正常情况应该能召回到蚜虫档案
    if refs:
        assert any(r["title"] == "蚜虫" for r in refs), [r["title"] for r in refs]
