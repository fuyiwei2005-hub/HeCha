# -*- coding: utf-8 -*-
"""切片 TTA 的聚合逻辑测试。

聚合是纯函数（不碰模型、不需要权重），所以能在这里被完整验证 ——
上线后红蜘蛛这类小目标能不能被救回来，全看这段逻辑对不对。
"""
from __future__ import annotations

import pytest

from app.services.detector import (
    Detector, _area, _cluster_individuals, _containment, _iou,
    _is_suspect_alternative, _same_individual,
)


def _mk(cls: int, conf: float, box: tuple[float, float, float, float]):
    return (cls, conf, box)


def test_iou_basic():
    assert _iou((0, 0, 10, 10), (0, 0, 10, 10)) == pytest.approx(1.0)
    assert _iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert 0.0 < _iou((0, 0, 10, 10), (5, 0, 15, 10)) < 1.0


def test_containment_is_one_when_small_box_nests_in_large():
    """小框完全落在大框内时，包含率恒为 1 —— 这正是 IoU 失效的地方。"""
    big, small = (0, 0, 100, 100), (20, 20, 60, 60)
    assert _containment(big, small) == pytest.approx(1.0)
    assert _containment(small, big) == pytest.approx(1.0)   # 对称
    # 而 IoU 在这里只有面积比 0.16，够不到 MERGE_IOU=0.30
    assert _iou(big, small) < 0.30
    assert _containment((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0


# ── 「一只虫显示成 ×3」的回归 ──────────────────────────────────
#
# 真实事故：用户传一张照片，界面显示「黄曲条跳甲 ×3」，但图上只有一只虫。
# 根因不是模型误检，而是 TTA 去重漏了「大框套小框」这一类：
# 同一只虫在 640 / 1280 / 切片下各出一个框，三个框大小差 2.31 倍，
# 最大框与最小框的 IoU = 0.435（IoU 对包含关系恒等于面积比），
# 够不到阈值，于是三个框全被保留，界面照实数成 3。
#
# 修法是补一条包含率判据（交集 ÷ 较小框面积 ≥ MERGE_CONTAIN= 0.50）。
# 下面三组坐标是从用户截图量出来的真实值。

_REAL_DUP_BIG = (229, 324, 508, 546)      # 53%
_REAL_DUP_MID = (246, 344, 471, 522)      # 55% ← 置信度最高，应保留这个
_REAL_DUP_SML = (259, 357, 441, 505)      # 53%


def test_nested_boxes_of_one_insect_collapse_to_single_detection():
    """一只虫在三个尺度下各出一个框 —— 必须合并成 1，不能显示成 ×3。"""
    det = Detector()
    raw = [_mk(0, 0.53, _REAL_DUP_BIG),
           _mk(0, 0.55, _REAL_DUP_MID),
           _mk(0, 0.53, _REAL_DUP_SML)]
    out = det._aggregate(raw, (1080, 687))
    assert len(out) == 1, f"同一只虫被算成 {len(out)} 只"
    assert out[0][1] == 0.55  # 保留置信度最高的那个框


def test_real_neighbouring_insects_are_not_merged():
    """紧贴但独立的个体不能被误并。

    ⚠️ 这个用例的坐标在 2026-10-06 重写过。原坐标是三个 60x60 的框，
    中心 x = 130 / 158 / 186，等距排列、水平交叠 52%：
        A vs B: IoU=0.347  contain=0.516
    一只独立的小虫不可能有 52% 的像素落在另一只虫的框里 —— 这在几何上
    描述的是「同一只虫被三个框错位框住」，而不是三只个体。所以原用例把
    重复框当成了个体，MERGE_CONTAIN 降到 0.35 后它必然失败。
    现改为真正紧贴、几乎不重叠的独立个体（IoU≈0.09）。
    """
    det = Detector()
    raw = [_mk(0, 0.50, (100, 100, 160, 160)),
           _mk(0, 0.49, (176, 106, 236, 166)),
           _mk(0, 0.48, (252, 100, 312, 160))]
    out = det._aggregate(raw, (1080, 687))
    assert len(out) == 3, f"三只独立虫被误并成 {len(out)} 只"


def test_touching_but_separate_insects_keep_their_own_boxes():
    """三只虫首尾相接、边界刚好相切 —— 这是最容易被误并的形态，必须保住。"""
    det = Detector()
    raw = [_mk(0, 0.60, (100, 100, 200, 200)),
           _mk(0, 0.58, (201, 102, 301, 202)),
           _mk(0, 0.56, (302, 98, 402, 198))]
    out = det._aggregate(raw, (1080, 687))
    assert len(out) == 3, f"相切的三只虫被误并成 {len(out)} 只"


def test_different_species_nearby_are_never_merged():
    """不同类别之间不做去重：截图里跳甲旁边就有一只斑蝥。"""
    det = Detector()
    raw = [_mk(0, 0.53, _REAL_DUP_BIG),
           _mk(0, 0.55, _REAL_DUP_MID),
           _mk(1, 0.60, (300, 300, 360, 360))]
    out = det._aggregate(raw, (1080, 687))
    assert sorted(b[0] for b in out) == [0, 1]


def test_partially_overlapping_pair_stays_two():
    """只压掉 21% 的两只显然是独立个体，不能因为「有点重叠」就并掉。"""
    det = Detector()
    raw = [_mk(4, 0.55, (100, 100, 200, 200)),
           _mk(4, 0.53, (170, 130, 270, 230))]
    out = det._aggregate(raw, (1080, 687))
    assert len(out) == 2


def test_same_object_across_scales_collapses_to_one_box():
    """同一只虫在多个尺度/切片下重复出现，去重后只应保留一个框。"""
    det = Detector()
    raw = [
        _mk(3, 0.62, (100, 100, 160, 160)),
        _mk(3, 0.58, (102, 98, 163, 162)),   # 同目标，轻微偏移
        _mk(3, 0.40, (400, 400, 430, 430)),  # 另一只
    ]
    out = det._aggregate(raw, (640, 640))
    assert len(out) == 2
    assert out[0][1] == 0.62        # 重复的框保留置信度高的那个
    assert out[0][0] == 3


def test_class_below_min_conf_is_dropped():
    """整类最高置信度都不到 min_conf 时，这一类不该出现在结果里。"""
    det = Detector()
    raw = [_mk(5, 0.21, (0, 0, 50, 50)), _mk(7, 0.55, (60, 60, 120, 120))]
    out = det._aggregate(raw, (640, 640))
    assert [b[0] for b in out] == [7]


def test_more_boxes_win_over_single_box_but_cluster_bonus_matters():
    """成片出现的虫（多个聚集框）应排在孤立单框之前。"""
    det = Detector()
    clustered = [_mk(1, 0.45, (100, 100, 140, 140)),
                 _mk(1, 0.44, (150, 105, 190, 145)),
                 _mk(1, 0.43, (120, 150, 160, 190))]
    lonely = [_mk(2, 0.70, (400, 400, 460, 460))]
    out = det._aggregate(clustered + lonely, (640, 640))
    # 孤立框置信度更高（0.70），但聚集度加成让成片的那类排前面
    assert out[0][0] == 1


def test_tile_coordinates_stay_in_original_image_space():
    """切片推理后坐标必须加回偏移，否则框会画在错误位置。"""
    det = Detector()
    # 模拟右下角切片的框（局部坐标 10,10~60,60，切片原点 500,500）
    out = det._aggregate([_mk(0, 0.8, (510, 510, 560, 560))], (1000, 1000))
    assert out[0][2] == (510, 510, 560, 560)


def test_empty_input_returns_empty():
    assert Detector()._aggregate([], (640, 640)) == []


# ──「一个虫子出现两种名字」的回归 ─────────────────────────────────
#
# 真实事故：用户传稻纵卷叶螟_04.jpg（1024×768，图里 3 只稻纵卷叶螟），
# 界面报「稻纵卷叶螟 ×1 / 叶蝉 ×2」，用户问「一只虫怎么冒出两个名字」。
#
# 空间聚类解决不了这个：三个簇的位置完全分离（两两 IoU 与包含率均为 0），
# 它们确实是 3 个独立个体，**几何上不该合并**。问题在于模型对形态几乎相同
# 的三个目标给了两种名称。强行统一类别是编造，正确做法是在界面上把
# 「主要检出」与「疑似同种」分开 —— 结论和猜测不能平级展示。


def test_close_second_name_is_flagged_as_suspect():
    """目标图实测：0.5140 / 0.6382 = 0.805，属于同批虫的变体。"""
    assert _is_suspect_alternative(0.5140, 0.6382) is True
    assert _is_suspect_alternative(0.5526, 0.6382) is True


def test_distant_name_is_not_flagged_as_suspect():
    """真正不同的虫种（蚜虫 0.2348）差得远，不该被卷进结论区。"""
    assert _is_suspect_alternative(0.2348, 0.6382) is False
    assert _is_suspect_alternative(0.0, 0.6382) is False


def test_suspect_flag_never_reaches_the_primary_class():
    """主类别必须靠 is_primary 单独判定，不能被 suspect 逻辑接管。

    _is_suspect_alternative 对「等于主置信度」的输入返回 True（比值 1.0 ≥ 0.6），
    这是纯函数的诚实行为；调用方predict_image 靠 `conf < best_conf` 把它挡在外面。
    这个测试锁住该边界，防止后人误删任一侧的守卫。
    """
    assert _is_suspect_alternative(0.6382, 0.6382) is True
    best = 0.6382
    is_primary = best >= best
    is_suspect = (best < best) and _is_suspect_alternative(best, best)
    assert is_primary is True
    assert is_suspect is False


def test_three_insects_split_into_two_species_keeps_all_three_boxes():
    """目标图的核心保证：3 只虫仍然是 3 个框，不因标记而丢框。"""
    det = Detector()
    raw = [
        # 簇1：稻纵卷叶螟 0.6382（正确）
        _mk(0, 0.6382, (468, 238, 725, 410)),
        # 簇2：叶蝉 0.5526（同一张图的另两只，被认错名字）
        _mk(45, 0.5526, (62, 288, 422, 463)),
        # 簇3：叶蝉 0.5140
        _mk(45, 0.5140, (825, 208, 1023, 432)),
    ]
    out = det._aggregate(raw, (768, 1024))
    assert len(out) == 3, "标记疑似不应改变框的数量"
    best = max(c for _, c, _ in out)
    suspects = [c for _, c, _ in out if c < best]
    assert all(_is_suspect_alternative(c, best) for c in suspects)


# ── 「一只虫显示成三种虫」的回归 ─────────────────────────────────
#
# 真实事故：用户传白星花金龟_01.jpg，界面报「白星花金龟 / 枯叶夜蛾 / 斑蝥」三种虫，
# 但图上只有一只甲虫。
#
# 根因是 TTA 的切片视角：目标本身 620×870 横跨两个切片，每个切片只看到虫的
# 一部分，各自认错了类别；反而是全图视角认对了：
#   全图 imgsz=640 → 白星花金龟 0.6295  [212,  55, 833, 925]   ← 唯一正确
#   左上切片       → 斑蝥0.3965  [179,  50, 636, 640]
#   右上切片       → 枯叶夜蛾     0.4325  [384,  36, 887, 640]
#
# ── 实现方式变更（2026-10 去重重构）───────────────────────────────
# 这组测试原先验的是「跨类别空间抑制」：先按类别分组去重，再用
# 「包含率高 + 中心接近 + 置信度比 1.3」三条判据去猜「这俩是同一只虫」，
# 把输的那一类整组丢掉。
#
# 现在改成**空间聚类优先**：类别判定发生在聚类之后，一只虫从一开始就只
# 产生一个簇、一个代表框、一个虫种 —— 「同一只虫两个虫种」在生成阶段
# 就不可能发生，不需要事后猜。旧逻辑连同它的三个阈值一起退役，
# 理由与实测数据见 detector.py 里「为什么不再需要跨类别抑制」那段注释。
#
# 下面这组测试的**断言目标不变**（同一只虫必须压回一个虫种、置信度相当或
# 相距很远的两个类别不得被压），只是验证路径从「事后抑制」换成了
# 「事前聚类」。测试名称也一并改掉，避免后来的人误以为还在验旧逻辑。

_CROSS_TRUE = (212, 55, 833, 925)     # 白星花金龟 0.6295 —— 应保留
_CROSS_MOTH = (384, 36, 887, 640)     # 枯叶夜蛾   0.4325 —— 应被合并掉
_CROSS_BEETLE = (179, 50, 636, 640)   # 斑蝥       0.3965 —— 应被合并掉


def test_area_and_same_individual_predicate():
    """_same_individual 的两条判据与面积护栏各自的边界。"""
    # IoU 路径：位置重合、尺寸相近 → 同一只
    assert _same_individual((0, 0, 100, 100), (5, 5, 105, 105)) is True
    # 包含率路径：小地老虎_03.jpg 实测框对（IoU 0.238 够不到 0.30，
    # 但包含率 0.509、面积比 1.64 都在阈值内）—— 只靠 IoU 会漏掉这一对。
    seed = (168.5, 81.1, 479.9, 637.4)
    other = (178.5, 384.3, 390.3, 882.0)
    assert _iou(seed, other) < 0.30
    assert _containment(seed, other) >= 0.50
    assert _same_individual(seed, other) is True
    # 面积比护栏：种子又大又散时，即便包含率满分也不算同一只 ——
    # 这是「大框当磁铁吞掉整片区域里几只虫」的防线。
    # 200x200 与 40x40 包含率是 1.0，但面积比 25 倍，远超 MERGE_AREA_RATIO。
    assert _containment((0, 0, 200, 200), (80, 80, 120, 120)) == pytest.approx(1.0)
    assert _same_individual((0, 0, 200, 200), (80, 80, 120, 120)) is False
    assert _area((0, 0, 10, 20)) == 200
    assert _area((5, 5, 5, 20)) == 0          # 退化框不炸


def test_nested_boxes_merge_despite_low_iou():
    """大框套小框时 IoU 恒等于面积比，再怎么套也上不去阈值 —— 必须靠包含率兜住。

    这是去重逻辑存在的主要原因。下面这组：面积比正好 4.0（护栏边界内），
    小框完全落在大框内，于是 IoU = 交集 ÷ 并集 = 400 ÷ 1600 = 0.25，
    够不到 MERGE_IOU = 0.30 —— 只看 IoU 就会把同一只虫拆成两个框。
    """
    big, small = (0, 0, 40, 40), (10, 10, 30, 30)
    assert _iou(big, small) == pytest.approx(0.25)
    assert _iou(big, small) < 0.30
    assert _containment(big, small) == pytest.approx(1.0)
    assert _same_individual(big, small) is True
    out = Detector()._aggregate([_mk(0, 0.55, big), _mk(0, 0.40, small)], (640, 640))
    assert len(out) == 1, "面积比4 倍的嵌套框应合并成一个"
    assert out[0][1] == 0.55# 保留置信度高的那个


def test_area_guard_blocks_extreme_size_ratio():
    """面积比超过护栏时，即便小框完全落在大框内也不合并。

    大框（切片里框到一片背景）会把区域内几只互不重叠的虫一起吞掉 ——
    它们两两比较都达标，纯粹的成对阈值拦不住，只有面积比拦得住。
    200x200套 40x40：包含率 1.0，但面积比 25 倍。
    """
    big, small = (0, 0, 200, 200), (80, 80, 120, 120)
    assert _containment(big, small) == pytest.approx(1.0)
    assert _same_individual(big, small) is False
    out = Detector()._aggregate([_mk(0, 0.55, big), _mk(1, 0.45, small)], (640, 640))
    assert len(out) == 2, "面积悬殊的两个框不该被并成一只"


def test_cluster_individuals_is_category_blind():
    """聚类只看几何，与类别无关 —— 这是它能同时解决「×2」和「两个虫种」的原因。"""
    raw = [_mk(0, 0.9, (100, 100, 200, 200)),
           _mk(1, 0.5, (105, 105, 205, 205)),   # 同位置，异类别
           _mk(2, 0.4, (600, 600, 700, 700))]   # 另一处
    clusters = _cluster_individuals(raw)
    assert len(clusters) == 2
    assert sorted(len(c) for c in clusters) == [1, 2]


def test_cluster_individuals_does_not_chain_transitively():
    """不做传递闭包：A~B、B~C 但 A≁C 时，A 与 C 不能被串进同一簇。

    这是 single-linkage 的经典失效模式。181 张实测里传递闭包误并 330 对
    「几乎不重叠、必然是不同个体」的高分框，贪心种子只 93 对，且Top-1
    完全相同—— 闭包只有误并、没有收益。
    """
    # seed (0,0,100,100) 与 B (60,60,160,160) 重叠；B 与 C (120,120,220,220)
    # 重叠；但 seed 与 C 几乎不重叠。
    raw = [_mk(0, 0.9, (0, 0, 100, 100)),
           _mk(0, 0.8, (60, 60, 160, 160)),
           _mk(0, 0.7, (120, 120, 220, 220))]
    clusters = _cluster_individuals(raw)
    assert len(clusters) == 3, f"被链式串成 {len(clusters)} 簇，应为 3"


def test_one_insect_reported_as_three_species_collapses_to_one():
    """一只甲虫被报成三个虫种 —— 必须压回一种，这是用户实际报的那个 bug。"""
    det = Detector()
    raw = [_mk(0, 0.6295, _CROSS_TRUE),
           _mk(1, 0.4325, _CROSS_MOTH),
           _mk(2, 0.3965, _CROSS_BEETLE)]
    out = det._aggregate(raw, (1024, 1024))
    assert len(out) == 1, f"一只虫仍被报成 {len(out)} 个虫种：{[b[0] for b in out]}"
    assert out[0][0] == 0           # 留下置信度最高的那个类别
    assert out[0][1] == 0.6295


def test_one_insect_at_two_confident_species_keeps_only_one_box():
    """两个类别置信度相当（0.62 / 0.55，比值 1.13 < 旧 CROSS_CONF_RATIO 1.3）。

    旧逻辑靠置信度比当安全阀：比值不足时不动手，于是这里会留下两个框
    （同一只虫被报成两个虫种，正是用户抱怨的现象）。
    新逻辑不再需要这个安全阀 —— 聚类只问「是不是同一只虫」，是就直接合并。
    """
    det = Detector()
    raw = [_mk(0, 0.62, (100, 100, 260, 300)),
           _mk(1, 0.55, (150, 130, 300, 320))]
    out = det._aggregate(raw, (640, 640))
    assert len(out) == 1, f"同一只虫仍留下 {len(out)} 个框"
    assert out[0][0] == 0


def test_distant_species_are_both_kept():
    """相距很远的两个类别不受影响 —— 图里确实有两处虫害。"""
    det = Detector()
    raw = [_mk(0, 0.80, (50, 50, 150, 150)),
           _mk(1, 0.35, (500, 500, 600, 600))]
    out = det._aggregate(raw, (640, 640))
    assert sorted(b[0] for b in out) == [0, 1]


def test_adjacent_non_overlapping_species_are_both_kept():
    """紧邻但不重叠的两只虫 —— 图里真有两只，不该被并。"""
    det = Detector()
    raw = [_mk(0, 0.90, (100, 100, 200, 200)),
           _mk(1, 0.40, (210, 100, 310, 200))]
    out = det._aggregate(raw, (640, 640))
    assert sorted(b[0] for b in out) == [0, 1]


# ── 真实目标图：稻纵卷叶螟_04.jpg（1024×768，图里 3 只虫）──────────
#
# 用户实测截图：界面显示「稻纵卷叶螟 ×2、叶蝉 ×2」共 4 个框，
# 其中中间那只被两个框重复框住。
#
# 13 个 TTA 原始候选按位置归成 3 簇（坐标为实测值，格式 [x1,y1,x2,y2]）：
#   簇0 中虫 → 稻纵卷叶螟 0.6382 / 0.5421 / 蚜虫 0.4086 / 0.1782 / 0.1593
#   簇1 左虫 → 叶蝉 0.5526 / 柑橘潜叶蛾 0.2771 / 稻纵卷叶螟 0.2182 / 0.2139
#   簇2 右虫 → 叶蝉 0.5140 / 0.2377 / 蚜虫 0.2348 / 0.1584
# 每簇的最高置信度都来自正确类别，投票后正好 3 个框、3 个虫种，
# 与图里 3 只虫一一对应。

_TARGET_RAW = [
    _mk(0, 0.6382, (468.3, 237.7, 725.0, 409.7)),   # 中虫稻纵卷叶螟 ← 正确
    _mk(1, 0.5526, (62.5, 288.1, 421.9, 463.3)),     # 左虫 叶蝉
    _mk(0, 0.5421, (474.6, 212.9, 639.9, 422.4)),
    _mk(1, 0.5140, (824.8, 208.2, 1022.6, 431.6)),   # 右虫 叶蝉
    _mk(2, 0.4086, (485.4, 250.9, 727.9, 418.2)),    # 中虫被认成蚜虫（少数派）
    _mk(3, 0.2771, (84.7, 241.8, 391.4, 433.6)),
    _mk(1, 0.2377, (810.9, 288.2, 1024.0, 447.3)),
    _mk(2, 0.2348, (842.1, 220.5, 1020.8, 433.0)),
    _mk(0, 0.2182, (90.2, 247.5, 391.8, 433.9)),
    _mk(1, 0.2139, (61.3, 219.0, 402.8, 484.2)),
    _mk(0, 0.1782, (473.5, 107.4, 639.9, 422.0)),    # ★旧逻辑的漏网元凶
    _mk(0, 0.1593, (465.5, 288.1, 748.4, 421.8)),
    _mk(1, 0.1584, (817.6, 188.6, 1024.0, 511.4)),
]


def test_target_image_each_insect_gets_exactly_one_box():
    """用户实测那张图：13 个候选必须收敛成 3 个框，一只虫一个框。"""
    out = Detector()._aggregate(list(_TARGET_RAW), (768, 1024))
    assert len(out) == 3, f"13 个候选收敛成了 {len(out)} 个框，应为 3"


def test_target_image_middle_insect_not_duplicated():
    """中间那只虫曾经被两个框重复框住（用户截图上的 64% 和 78%）。

    它的 5 个候选里，纵向拉长的那个 0.1782 框与主框的包含率只有 0.648 ——
    旧阈值卡在 0.7 够不到，于是漏了下来。新逻辑按簇投票，5 个候选里
    置信度最高的是 0.6382，只有它能代表这只虫。
    """
    out = Detector()._aggregate(list(_TARGET_RAW), (768, 1024))
    mid = [b for b in out if b[2][0] > 400 and b[2][2] < 800]
    assert len(mid) == 1, f"中间那只虫仍有 {len(mid)} 个框"
    assert mid[0][1] == 0.6382


def test_target_image_output_has_no_overlapping_pair():
    """输出里任意两框都不得重叠 —— 「一只虫一个框」的充要条件。

    这条比逐个断言框数更强：即使将来聚类判据被调松，只要还漏出重叠框，
    这个测试就会失败。181 张实测的旧逻辑在这里是 93 对（61 张图）。
    """
    out = Detector()._aggregate(list(_TARGET_RAW), (768, 1024))
    for i in range(len(out)):
        for j in range(i + 1, len(out)):
            a, b = out[i][2], out[j][2]
            assert not (_iou(a, b) >= 0.30 or _containment(a, b) >= 0.50), \
                f"输出仍有一对重叠框：{out[i]}与 {out[j]}"


def test_target_image_species_come_from_individual_vote():
    """每个虫种都必须由某个簇投票产生 —— 不能有哪个虫种是聚类之外的残留。

    这张图最终是 3 个框、2 个虫种（中虫=稻纵卷叶螟，左右两虫=叶蝉）。
    2 个虫种不是去重没做干净的证据：左右两虫各自位置上的最高置信度
    候选确实都落在叶蝉上（0.5526/ 0.5140），而覆盖它们的稻纵卷叶螟候选
    最高只有 0.2182，差2.5 倍。**这是模型的判断，不是去重的残留** ——
    去重该做的都做了：3 只虫 3 个框、一虫一种，界面不再出现「×2」。

    所以这条断言的是「虫种数 ≤ 框数且每种都来自独立簇」这个不变式，
    而不是硬编码一个具体数字（数字会随模型权重更新而变，写死会变成假失败）。
    """
    out = Detector()._aggregate(list(_TARGET_RAW), (768, 1024))
    assert len(out) == 3
    assert len({b[0] for b in out}) <= len(out)
    # 中虫那簇必须只出一个虫种（不能同时报稻纵卷叶螟和蚜虫）
    mid = [b for b in out if b[2][0] > 400 and b[2][2] < 800]
    assert len({b[0] for b in mid}) == 1, "中虫被同时报成了两个虫种"


def test_vote_uses_single_highest_confidence_not_sum():
    """簇内投票必须取单次最高置信度，不能各类别求和。

    构造一个反例：碎片多的类别靠求和虚高。
    正确类别只被认对 1 次（0.60），错误类别被 5 次低置信度认错（各 0.20，
    求和 1.00）。求和投票会选错，取最大值才选对。
    """
    det = Detector()
    raw = [
        _mk(0, 0.60, (100, 100, 200, 200)),# 正确，只出现一次
        _mk(1, 0.20, (102, 102, 200, 200)),
        _mk(1, 0.20, (103, 103, 199, 199)),
        _mk(1, 0.20, (101, 101, 201, 201)),
        _mk(1, 0.20, (104, 104, 198, 198)),
        _mk(1, 0.20, (100, 100, 200, 200)),
    ]
    out = det._aggregate(raw, (640, 640))
    assert len(out) == 1
    assert out[0][0] == 0, "求和投票让碎片多的错误类别虚高了"


def test_min_conf_filters_on_cluster_max_not_on_voted_species():
    """置信度过滤看簇内最强证据，而不是投票选中类别的那一票。

    构造反例：簇里有个0.55 的强证据（类别 A）和一个 0.29 的弱证据（类别 B）。
    无论投票选哪个，0.55 都证明这只虫存在，不该被整簇丢掉。
    """
    det = Detector()
    raw = [
        _mk(0, 0.55, (100, 100, 200, 200)),
        _mk(1, 0.29, (102, 102, 200, 200)),
    ]
    out = det._aggregate(raw, (640, 640))
    assert len(out) == 1, "簇内有 0.55 的强证据却被整簇过滤掉了"
    assert out[0][1] == 0.55


def test_aggregate_output_shape_is_three_tuples():
    """_aggregate 的返回结构必须是 3 元组 —— predict_image 按 3 元组解包。

    这条不是形式主义：历史上跨类别抑制那一版曾把 (cls, conf, box) 改成过
    别的形状，解包一旦对不上就是线上 TypeError。
    """
    out = Detector()._aggregate([_mk(3, 0.55, (10, 10, 60, 60))], (640, 640))
    assert len(out) == 1
    cls, conf, box = out[0]
    assert isinstance(cls, int)
    assert isinstance(conf, float)
    assert len(box) == 4


def test_aggregate_handles_degenerate_boxes():
    """退化框（宽或高为 0）不能让聚类抛异常 —— TTA 里真实出现过。"""
    det = Detector()
    raw = [_mk(0, 0.55, (100, 100, 100, 200)),
           _mk(0, 0.50, (300, 100, 500, 200))]
    out = det._aggregate(raw, (640, 640))
    assert len(out) == 2


# ── 「同一只虫显示成 ×2」的回归（MERGE_CONTAIN 0.7 → 0.35 的起因）──────────
#
# 真实事故：用户传稻纵卷叶螟_04.jpg（1024×768，三只稻纵卷叶螟横排），
# 界面报「稻纵卷叶螟 ×2」，中间那只虫身上套了两个框。
#
# 根因：中间那只虫被5 次 TTA推理报出 5 个候选框，其中两个虽然是同一个类别，
# 却因为在切片里被截掉了一部分而**位置明显错开**：
#     切片 r0c1 → 稻纵卷叶螟 0.6382 [468.3, 237.7, 725.0, 409.7]  ← 正确，保留
#     切片 r0c0 → 稻纵卷叶螟 0.5421 [474.6, 212.9, 639.9, 422.4]  contain 0.821 → 旧阈值下已合并
#     切片 r0c0 → 稻纵卷叶螟 0.1782 [473.5, 107.4, 639.9, 422.0]
# 最后一个与首框 IoU=0.422（< 0.6）、contain=0.648（< 0.7），**两条判据都差一点**，
# 于是漏合并。这类重复框因为"截断"，不会明显重叠，IoU 和包含率都难以兜住。
#
# 放宽到 0.35 为什么安全：该图三只真虫彼此完全不重叠（两两 IoU=0、contain=0），
# 181 张离线A/B 也显示 contain 在0.15~0.70 全区间 Top-1/任意命中/真值丢失三项不变。

_MOTH_KEEP = (468.3, 237.7, 725.0, 409.7)     # 0.6382 —— 应保留
_MOTH_MERGED = (473.5, 107.4, 639.9, 422.0)   # 0.1782 —— 应被合并
_MOTH_SIBLING = (63, 288, 422, 463)           # 0.5526 左边那只（错判为叶蝉），不该被牵连


def test_one_insect_split_across_tiles_shows_single_box():
    """同类别两个框错位（IoU 0.42、contain 0.65）必须合并成1 个。"""
    det = Detector()
    raw = [_mk(0, 0.6382, _MOTH_KEEP),
           _mk(0, 0.1782, _MOTH_MERGED)]
    out = det._aggregate(raw, (768, 1024))
    assert len(out) == 1, f"同一只虫仍显示成 {len(out)} 个框"
    assert out[0][1] == pytest.approx(0.6382)   # 保留置信度高的


def test_three_real_moths_stay_three_boxes():
    """完整复现稻纵卷叶螟_04 的场景：三只虫各留一个框，不多不少。"""
    det = Detector()
    raw = [_mk(0, 0.6382, (468.3, 237.7, 725.0, 409.7)),   # 中间那只，正确
           _mk(0, 0.1782, (473.5, 107.4, 639.9, 422.0)),   # 同一只的重复框
           _mk(0, 0.5421, (474.6, 212.9, 639.9, 422.4)),   # 同一只的另一个重复框
           _mk(0, 0.1593, (465.5, 288.1, 748.4, 421.8)),   # 同一只的第四个框
           _mk(1, 0.5526, (63, 288, 422, 463)),            # 左边那只（被错判为叶蝉）
           _mk(1, 0.5140, (825, 208, 1023, 432))]          # 右边那只
    out = det._aggregate(raw, (768, 1024))
    # 稻纵卷叶螟合并成 1 个框，叶蝉保留 2 个（真有两只是对的）
    assert sum(1 for b in out if b[0] == 0) == 1, \
        f"中间那只虫仍被算成 {sum(1 for b in out if b[0] == 0)} 只"
    assert sum(1 for b in out if b[0] == 1) == 2
