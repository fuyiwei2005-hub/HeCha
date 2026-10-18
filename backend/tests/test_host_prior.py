"""寄主先验的安全性质测试。

这里测的不是「准确率有没有提升」（那是评测集的事），
而是**这套先验在最坏情况下会不会害人**。每一条都对应一个真实的失败场景。
"""
from __future__ import annotations

import copy

import pytest

from app.services.host_prior import HostPrior, DATA_PATH


@pytest.fixture(scope="module")
def hp() -> HostPrior:
    p = HostPrior()
    if not p.available:
        # 这里**不能** skip：先验表是运行时必需文件，不是可选依赖。
        # 之前是 skip，于是在没有该文件的机器上（例如干净 clone）会静默跳过
        # 33 个用例，整套测试看起来"通过"，而寄主先验功能其实已经废了。
        # 缺文件必须是一个响亮的失败。
        pytest.fail(
            f"先验表不可用：{p.load_error}\n"
            f"  文件位置：{DATA_PATH}\n"
            "  这是运行时必需文件，必须随仓库一起分发。\n"
            "  如果你是从 git clone 拿到的代码，说明它被 .gitignore 排除了 —— "
            "请确认 .gitignore 里没有整体忽略 backend/data/。"
        )
    return p


def _pred(cls_cn: str, conf: float) -> dict:
    return {"class": cls_cn, "class_cn": cls_cn, "confidence": round(conf, 4)}


# ── 1. 数据完整性 ────────────────────────────────────────────────────
def test_prior_table_covers_all_model_classes(hp):
    """先验表必须覆盖全部 46 类，缺一类就说明知识库与模型不同步。"""
    from app.services.pest_names import CLASS_CN

    data = hp._load()
    missing = [cn for cn in CLASS_CN.values() if cn not in data["pests"]]
    assert not missing, f"先验表缺失模型类别：{missing}"


def test_crop_integrity(hp):
    """有先验的作物：候选非空、strong/related 不重叠。"""
    crops = hp._load()["crops"]
    assert any(c.get("has_prior") for c in crops), "没有任何作物带先验，表是空的"

    for c in crops:
        strong, related = set(c["strong"]), set(c["related"])
        assert not (strong & related), f"{c['key']} 的 strong/related 有重叠：{strong & related}"
        if c.get("has_prior"):
            assert strong or related, f"{c['key']} 标记了 has_prior 却没有候选"
        else:
            # 无先验作物靠 has_prior=False 走「不动」分支，必须真的没有候选
            assert not strong and not related, f"{c['key']} 无先验却有候选，标记不一致"


def test_no_prior_crop_never_punishes(hp):
    """选了没有先验的作物（如番茄），绝不能反过来惩罚专性害虫 —— 那是无依据降权。"""
    no_prior = [c["key"] for c in hp._load()["crops"] if not c.get("has_prior")]
    assert no_prior, "需要有至少一个无先验作物来覆盖这条路径"
    for crop in no_prior:
        for pest in ("柑橘锈螨", "稻纵卷叶螟", "葡萄天蛾", "小麦管蓟马"):
            level, alpha = hp.level_of(pest, crop)
            assert level == "neutral", f"{pest}@{crop} 被误判为 {level}（无先验作物应完全不干预）"
            assert alpha == 0.0


# ── 1b. 作物显示名与别名 ────────────────────────────────────────────
def test_single_char_crops_have_display_label(hp):
    """单字作物名（李/柿…）直接展示会被读成「名字不全」，必须有显示名。"""
    for c in hp.crops():
        if len(c["key"]) == 1:
            assert len(c["label"]) >= 2, (
                f"{c['key']} 的显示名仍是单字「{c['label']}」，下拉框里读起来像名字写了一半"
            )


def test_label_is_purely_display_key_unchanged(hp):
    """显示名只影响展示，key 必须保持原样 —— key 是映射主键，也进了数据库。"""
    assert hp.resolve_crop("李子") == "李"
    assert hp.display_name("李") == "李子"
    # 先验结果里同时给出两者，写库用 key、给大模型用 label
    res = hp.rerank([_pred("桃蛀螟", 0.5)], "李子")
    assert res.crop == "李"
    assert res.crop_label == "李子"


@pytest.mark.parametrize(
    "alias,key", [("李子", "李"), ("柿子", "柿"), ("西红柿", "番茄"), ("土豆", "马铃薯")]
)
def test_colloquial_alias_resolves(hp, alias, key):
    """用户手输口语写法也必须生效。不认别名会让先验静默失效（判为未知作物），
    用户以为选了作物其实什么都没做 —— 比报错更糟。"""
    assert hp.resolve_crop(alias) == key
    assert hp.known_crop(alias)


def test_alias_and_key_give_same_result(hp):
    """别名与 key 必须产出完全一致的重排结果，不能有两套行为。"""
    a = hp.rerank([_pred("桃蛀螟", 0.5)], "李")
    b = hp.rerank([_pred("桃蛀螟", 0.5)], "李子")
    assert [p["confidence"] for p in a.predictions] == [p["confidence"] for p in b.predictions]
    assert a.predictions[0]["prior"]["level"] == b.predictions[0]["prior"]["level"]


def test_junk_crop_still_rejected(hp):
    """别名扩展不能把未知作物放进来 —— 清单外一律不动的原则不变。"""
    for bad in ("榴莲", "", "   ", "李子树上", None):
        assert hp.resolve_crop(bad) is None, f"{bad!r} 不该被识别为已知作物"


def test_llm_hint_uses_display_name(hp):
    """prompt 里用「李子」而不是「李」：单字作物名容易被模型当普通汉字读过。"""
    hint = hp.hint_for_llm("李子", [_pred("桃蛀螟", 0.9)])
    assert "拍摄作物：李子" in hint


# ── 2. 安全底线：绝不吞掉检出结果 ──────────────────────────────────
def test_never_drops_detection_on_conflict(hp):
    """物种是最致命的失败模式：作物选错导致真害虫消失。

    场景：柑橘锈螨出现在小麦田（用户选错作物），它必须还在候选里。
    """
    preds = [_pred("柑橘锈螨", 0.80), _pred("小麦管蓟马", 0.30)]
    res = hp.rerank(copy.deepcopy(preds), "小麦")

    assert len(res.predictions) == len(preds), "检出数量被改变了，这是致命回归"
    names = [p["class_cn"] for p in res.predictions]
    assert "柑橘锈螨" in names, "冲突候选被丢弃 —— 违反「永不置零」约束"
    mite = next(p for p in res.predictions if p["class_cn"] == "柑橘锈螨")
    assert mite["prior"]["level"] == "conflict"
    assert mite["ranking_score"] > 0, "冲突候选排序分数被压到 0"
    assert mite["confidence"] == 0.80


def test_conflict_weight_has_hard_floor(hp):
    """冲突降权必须受 floor 保护，不能比预设更狠。"""
    sc = hp.scoring
    res = hp.rerank([_pred("柑橘锈螨", 0.9999)], "小麦")
    p = res.predictions[0]
    assert p["ranking_score"] >= 0.9999 * sc.floor - 1e-6, (
        f"权重低于 floor 底线：{p['ranking_score']} < {0.9999 * sc.floor}"
    )


def test_preserves_original_confidence(hp):
    """保留原始置信度，便于评测与前端展示「原始 → 加权」。"""
    res = hp.rerank([_pred("稻纵卷叶螟", 0.62)], "水稻")
    assert res.predictions[0]["raw_confidence"] == 0.62
    assert res.predictions[0]["confidence"] == 0.62


def test_input_not_mutated(hp):
    """rerank 不得原地改传入对象 —— 调用方可能还要用原始结果入库。"""
    preds = [_pred("柑橘锈螨", 0.8)]
    snapshot = copy.deepcopy(preds)
    hp.rerank(preds, "小麦")
    assert preds == snapshot, "入参被修改，会产生难以排查的副作用"


# ── 3. 广谱害虫绝不动 ────────────────────────────────────────────────
@pytest.mark.parametrize(
    "pest", ["蚜虫", "蓟马", "红蜘蛛", "蛴螬", "斜纹夜蛾", "叶蝉", "盲蝽", "蝗虫"]
)
def test_broad_pests_never_adjusted(hp, pest):
    """蚜虫这类在哪都有的虫，一旦加权就等于在所有作物上都放大，纯属噪声。"""
    for crop in ("水稻", "小麦", "葡萄", "柑橘", "玉米"):
        level, alpha = hp.level_of(pest, crop)
        assert level == "neutral", f"{pest}@{crop} 被判为 {level}，应为 neutral"
        assert alpha == 0.0


# ── 4. 正向强化 ──────────────────────────────────────────────────────
def test_strong_match_boosts(hp):
    res = hp.rerank([_pred("稻纵卷叶螟", 0.50)], "水稻")
    p = res.predictions[0]
    assert p["prior"]["level"] == "strong"
    assert p["ranking_score"] > p["confidence"] == p["raw_confidence"]


def test_prior_can_change_ranking(hp):
    """核心收益：先验能让「该作物的典型虫」从第二名提到第一名。"""
    # 蚜虫(广谱) 0.72 vs 葡萄根瘤蚜 0.58 —— 原始看蚜虫在前
    preds = [_pred("蚜虫", 0.72), _pred("葡萄根瘤蚜", 0.58)]
    before = [p["class_cn"] for p in preds]
    res = hp.rerank(copy.deepcopy(preds), "葡萄")
    after = [p["class_cn"] for p in res.predictions]

    assert before[0] == "蚜虫"
    assert after[0] == "葡萄根瘤蚜", f"寄主先验未能纠正排序：{after}"
    assert res.applied


def test_counts_are_conserved(hp):
    preds = [_pred("蚜虫", 0.6), _pred("柑橘锈螨", 0.5), _pred("葡萄天蛾", 0.4)]
    res = hp.rerank(copy.deepcopy(preds), "柑橘")
    assert len(res.predictions) == 3
    assert sorted(p["class_cn"] for p in res.predictions) == sorted(p["class_cn"] for p in preds)


# ── 5. 降级与容错 ────────────────────────────────────────────────────
def test_unknown_crop_is_noop(hp):
    """用户填了个不在表里的作物，必须原样返回，不能猜。"""
    preds = [_pred("蚜虫", 0.6)]
    res = hp.rerank(copy.deepcopy(preds), "榴莲")
    assert not res.applied
    assert res.predictions == preds
    assert "未知作物" in res.reason


def test_missing_table_does_not_crash(tmp_path):
    """先验表丢失时，检测主链路不能受影响。"""
    broken = HostPrior(tmp_path / "nope.json")
    assert not broken.available
    assert broken.load_error
    res = broken.rerank([_pred("蚜虫", 0.6)], "水稻")
    assert not res.applied
    assert len(res.predictions) == 1


def test_corrupted_table_is_reported(tmp_path):
    bad = tmp_path / "host_prior.json"
    bad.write_text("{ this is not json", encoding="utf-8")
    broken = HostPrior(bad)
    assert not broken.available
    assert "损坏" in (broken.load_error or "")


def test_empty_crop_and_empty_preds(hp):
    assert hp.rerank([], "水稻").applied is False
    res = hp.rerank([_pred("蚜虫", 0.6)], None)
    assert not res.applied and res.predictions[0]["confidence"] == 0.6


# ── 6. 大模型上下文 ──────────────────────────────────────────────────
def test_llm_hint_mentions_crop(hp):
    hint = hp.hint_for_llm("葡萄", [_pred("葡萄根瘤蚜", 0.9)])
    assert "葡萄" in hint and "葡萄根瘤蚜" in hint
    assert "安全间隔期" in hint


def test_llm_hint_warns_on_conflict(hp):
    """冲突时提示必须让用户「复核」，而不是替他下结论。"""
    hint = hp.hint_for_llm("小麦", [_pred("柑橘锈螨", 0.9)])
    assert "复核" in hint or "不要直接下结论" in hint


def test_llm_hint_without_crop(hp):
    assert hp.hint_for_llm(None, [_pred("蚜虫", 0.6)]) == ""


# ── 7. 元数据诚实性 ──────────────────────────────────────────────────
def test_scoring_defaults_are_conservative(hp):
    """alpha 必须小于 socalled 激进值，且 floor 必须为正 —— 防误伤的护栏。"""
    sc = hp.scoring
    assert 0 < sc.floor < 1, "floor 必须在 (0,1)"
    assert sc.alpha_strong <= 0.5, "alpha_strong 过大，模型置信度会被先验压过"
    assert sc.alpha_conflict < 0
    assert sc.floor >= 0.3, "floor 太低等于变相置零"
    KEY = "校准"
    assert KEY in sc.note, "scoring.note 必须写明未经评测校准，防止被当成结论引用"


def test_data_path_exists():
    """CI 兜底：先验表必须已随仓库生成。"""
    assert DATA_PATH.is_file(), f"缺少 {DATA_PATH}，请运行 tools/build_host_prior.py"
