import io
import logging
import math
import os
from collections import defaultdict
from pathlib import Path
from threading import Lock
from typing import Any

from PIL import Image, ImageDraw
import numpy as np

from app.core.config import get_settings
from app.services.annotate import draw_labels
from app.services.pest_names import to_chinese


logger = logging.getLogger(__name__)

TILE_OVERLAP = 0.25

# ── 空间聚类去重（一只虫一个框 + 一个虫种）────────────────────────────
#
# 下面这两条判据属于「按类别去重」时代：先按类别分组、组内 NMS、再跨类别抑制。
# 它的结构缺陷是**同类别判定发生在空间聚类之前** —— 同一只虫在切片里被认成虫种 A、
# 在全图里被认成虫种 B 时，A 组和 B 组互相看不见，各自都认为「组内没有重复」，
# 于是各留一个框。TTA 跑 5 次（1 全图 + 4 切片），实测 350 个个体里有 249 个
# （71.1%）被 2~11 个框重复覆盖，界面就显示成「稻纵卷叶螟 ×2」甚至「×11」，
# 并且同一只虫被报成两个虫种。
#
# 阈值不是拍脑袋定的，来自 181 张人工复核图里 1186 个候选框的成对几何关系。
# 先把候选框按「个体」聚类，再统计簇内（同一只虫的重复框）与簇间（不同真个体）
# 两类框对的分离度：
#
#                簇内重复框对          簇间真个体对
#     对数                2407            566
#     包含率 p50          0.938          —
#     包含率 max          1.0             0.4981
#     包含率 p99          1.0             0.4911
#     IoU    max          0.9953          0.2917
#
# 两组分布之间有一整段空隙：包含率 0.50~0.94 无任何框对，IoU 0.2917~0.9953 同理。
# 所以阈值取在空隙里而不是贴着簇内下界 ——
# MERGE_CONTAIN = 0.50（簇内 p50 的 0.938 与簇间上限 0.4981 之间）
# MERGE_IOU     = 0.30（簇间上限 0.2917 之上，留一点余量）
MERGE_IOU = 0.30
MERGE_CONTAIN = 0.50

# 面积比护栏：走「包含率」这条路径合并时，两框面积不能悬殊。
#
# 为什么需要它：贪心聚类是「一颗种子吸收所有与它达标的框」。若种子是个又大又散的
# 框（切片里框到一片背景很常见，实测单框面积可达 56 万像素²），它就能把区域内
# 两只互不重叠的虫一起吞掉 —— 两两比较全都达标，纯粹的成对阈值拦不住，
# 因为它们不是「互相」合并的，是「都被同一颗种子合并的」。
# 181 张实测这类「磁吸」事件共 37 次（同一份数据把护栏关掉复算出来的；
# 护栏打开后这 37 次全部不再发生，簇总数 350 → 381）。
#
# 取 4.0：同一只虫的 TTA 重复框面积比实测都在 2 倍以内（已知最大 2.31倍，
# 见下面黄曲条跳甲那个案例），4.0 留了一倍余量；再往下收会开始拆散同一只虫。
MERGE_AREA_RATIO = 4.0

# ── 为什么不再需要跨类别抑制 ────────────────────────────────────────
#
# 原先有一组 CROSS_CONTAIN/CROSS_CENTER/CROSS_CONF_RATIO 专门收拾
# 「同一只虫被认成多个虫种」，实测能压掉 32% 的多虫种图（25 张 → 17 张）。
# 现在这套逻辑退役，因为它要解决的问题在根上不存在了：
#
#   旧结构：类内去重（按 cls 分组）→ 跨类别抑制。跨类别抑制必须靠
#           「包含率高 + 中心接近 + 置信度比 1.3」三条判据去猜「这俩是同一只虫」，
#           猜错了就会把图里真有两处虫害的地方也压掉一只 —— 这是它最大的风险。
#   新结构：空间聚类在**类别判定之前**完成，一只虫从一开始就只产生一个簇、
#           一个代表框、一个虫种。「同一只虫两个虫种」在生成阶段就不可能发生，
#           不需要事后猜。181 张实测 ≥3 虫种的图 17 张 → 3 张，
#           比旧结构单用跨类别抑制的 17 张更好，而且是零猜测成本拿到的。
#
# 对应的白星花金龟_01 案例（同一只甲虫被报成白星花金龟/斑蝥/枯叶夜蛾三种，
# 因为目标 620×870 横跨两个切片、各自认错类别）现在由聚类直接解决：
# 三个框落进同一簇，取簇内最高置信度的那个类别。
#
# 保留旧行为的测试见 tests/test_detector_tta.py，
# test_one_insect_reported_as_three_species_collapses_to_one 已按新结构重写。

# 包含率（intersection over smaller）的含义与选值依据见上面 MERGE_CONTAIN。
# 单独解释为什么 IoU 单独用不够：IoU = 交集 ÷ 并集，小框落在大框内部时
# 交集 ≈ 小框面积、并集 ≈ 大框面积，于是 IoU ≈ 面积比 —— 大框套小框时
# 无论套得多紧IoU 都上不去。实测黄曲条跳甲三个框大小差 2.31 倍，
# 最大框与最小框 IoU 仅 0.435，够不到任何合理阈值，三个框会全留下。
# 所以必须配一条以「较小框」为分母的包含率判据。


def _iou(a, b) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    sa = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    sb = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return inter / (sa + sb - inter + 1e-9)


def _containment(a, b) -> float:
    """交集面积 ÷ 较小框面积。1.0 表示小框完全落在大框内部。

    与 IoU 的区别：IoU 用并集做分母，框大小悬殊时会被大框稀释；
    这里用较小的那个框做分母，所以「谁被装进去」始终是 1.0，不受大小影响。
    """
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    sa = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    sb = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    smaller = min(sa, sb)
    return inter / smaller if smaller > 0 else 0.0


def _area(box) -> float:
    """框面积。退化框（宽或高为 0）返回 0，不会除零。"""
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _same_individual(seed_box, other_box) -> bool:
    """两个框是否指向同一只虫：空间聚类的唯一判据。

    两条几何判据取或：
    - MERGE_IOU：抓「位置重合、尺寸相近」的常规情形；
    - MERGE_CONTAIN：抓「大框套小框」。这类重复的 IoU 恒等于面积比，
      无论套得多紧都上不去阈值（见上面 _containment 的说明）。

    面积比护栏只挂在包含率这条路径上：IoU 本身已经隐含了「两框大小相当」
    （两个悬殊的框不可能有高 IoU），而包含率没有这个约束，一个 56 万像素²
    的大框能装下任何小框。护栏的作用是防止这种大框当「磁铁」把整片区域里
    几只互不重叠的虫一次吞掉 —— 那两只虫两两比较都达标，拦不住，
    因为它们不是互相合并的，是被同一颗种子一起吸收的。
    """
    if _iou(seed_box, other_box) >= MERGE_IOU:
        return True
    if _containment(seed_box, other_box) < MERGE_CONTAIN:
        return False
    sa, sb = _area(seed_box), _area(other_box)
    if sa <= 0.0 or sb <= 0.0:
        return False
    return max(sa, sb) <= MERGE_AREA_RATIO * min(sa, sb)


def _cluster_individuals(raw: list[tuple]) -> list[list[tuple]]:
    """把候选框聚成「个体簇」，与类别无关。返回 list[list[候选框]]。

    贪心种子聚类：按置信度降序遍历，取第一个未被吸收的框做种子，
    把它周围所有满足 _same_individual 的框一并收进簇里，然后处理下一个种子。

    刻意**不做传递闭包**。「A 与 B 重叠、B 与 C 重叠 ⇒ A/B/C 同簇」这条直觉
    规则在这里是错的：它是 single-linkage 聚类的经典失效模式，链一长就会把
    整片区域串成一个簇。实测（181 张图里「同图内彼此几乎不重叠、必然是
    不同个体」的高分框对，统一口径 conf≥0.30、IoU<0.2917、包含率<0.4981）：
        传递闭包误并 315 对/ 71 张图
        贪心种子   误并 90 对 / 44 张图   ← 本函数 + 面积护栏
    而两者 Top-1 完全相同（都是 87/181）—— 闭包只带来了误并，没带来任何收益。

    复杂度 O(n²)。单图候选框实测 0~45 个（有 5 张图零候选），n² 最大 2025次
    框比较，每次只是几次浮点运算，相对一次推理可以忽略。
    """
    order = sorted(range(len(raw)), key=lambda i: -raw[i][1])
    taken = [False] * len(raw)
    clusters: list[list[tuple]] = []
    for i in order:
        if taken[i]:
            continue
        taken[i] = True
        cluster = [raw[i]]
        for j in order:
            if taken[j]:
                continue
            if _same_individual(raw[i][2], raw[j][2]):
                taken[j] = True
                cluster.append(raw[j])
        clusters.append(cluster)
    return clusters


def _cluster_bonus(items, size) -> float:
    """同类框的空间聚集度（0~1）。真害虫常常成片出现，孤立噪声框不该被当成主要害虫。"""
    if len(items) < 2:
        return 0.0
    h, w = size
    diag = math.hypot(h, w)
    centers = [((b[2][0] + b[2][2]) / 2, (b[2][1] + b[2][3]) / 2) for b in items]
    near = sum(1 for i in range(len(centers)) for j in range(i + 1, len(centers))
               if math.dist(centers[i], centers[j]) < diag * 0.18)
    pairs = len(centers) * (len(centers) - 1) / 2
    return near / pairs


# ── 主结论 / 疑似 ────────────────────────────────────────────────────
#
# 空间聚类解决了「一只虫多个框」，但解决不了「同一批虫被报成两个名字」。
# 典型案例 稻纵卷叶螟_04.jpg（1024×768，图里 3 只稻纵卷叶螟）：
#     簇1 → 稻纵卷叶螟 0.6382
#     簇2 → 叶蝉       0.5526   ← 同一张图、同样形态的虫
#     簇3 → 叶蝉       0.5140
# 三个簇的空间位置完全分离（IoU 与包含率均为 0），**几何上无法也不应该合并**——
# 它们确实是 3 个独立个体。问题在于：同一次检测里，模型对形态几乎相同的
# 三个目标给出了两种名字，界面上「稻纵卷叶螟 ×1」「叶蝉 ×2」并排显示，
# 用户看到的就是「一只虫子冒出两个名字」。
#
# 为什么不在后端强行统一类别：试过图级归并（少数派簇若含主类别候选就跟随），
# 181 张实测Top-1 恒为 87、虫种数仅 197→193，而目标图**仍收敛不了**——
# 簇3 里一个稻纵卷叶螟候选都没有，没有任何跟随依据，强行改就是编造。
# 这类错误属于「模型能力边界」，不该用后处理掩盖。
#
# 所以改为**如实分层展示**：最高分类别作为「主要检出」，其余类别标注为
# 「疑似同种」。这不是隐藏信息，而是把结论和猜测在界面上分开——
# 农户看到「主要检出：稻纵卷叶螟（3）」比看到两个平级虫种更可信，
# 也更符合「不确定就明说」的产品原则。低置信度的第二候选仍然可见、可追问。
#
# 判定条件（两者都满足才算「疑似同种」）：
#   1) 该类别最高置信度 ≥ 阈值：太低说明连猜测都不成形，不该混进结论区
#   2) 该类别与主类别的置信度接近：差太多说明确实是另一个虫种，不该归并
PRIMARY_CONF_RATIO = 0.60


def _is_suspect_alternative(conf: float, primary_conf: float) -> bool:
    """这个类别是否只是主结论的一个低置信度变体（同批虫被认错名字）。

    只用置信度比值判定，不碰几何 —— 几何上它们本来就是分离的个体。
    比值取 0.60：主类别 0.6382 时，0.5140 / 0.6382 = 0.805 会被判为疑似；
    而真正不同的虫种（差一个数量级）比值远低于 0.60，不会被卷进来。
    """
    if primary_conf <= 0:
        return False
    return conf >= primary_conf * PRIMARY_CONF_RATIO


class Detector:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._model: Any = None
        # 加载锁只保护"模型单例的创建"，不能顺手用来保护推理 ——
        # 否则加载完成后它就形同虚设，而推理还在被多线程并发调用。
        self._lock = Lock()
        # 推理锁：PyTorch 的 forward 不是线程安全的。API 用 asyncio.to_thread
        # 把推理丢进线程池，公网多用户并发上传时会同时调同一个 YOLO 实例，
        # 结果是进程崩溃或检测框错乱。这里让推理串行化。
        self._infer_lock = Lock()

    @property
    def ready(self) -> bool:
        """模型是否已加载。

        探活接口要能区分「服务活着」和「服务能干活」：权重没加载时
        接口照样返回 200，但第一次检测要现场加载几秒 —— 监控必须看得到。
        """
        return self._model is not None

    @property
    def mode(self) -> str:
        """真实模型 / 演示检测器 / 配了路径但加载不了。

        注意不能用 `"yolo" if model_path else "mock"`：那样只要配了路径就报 yolo，
        哪怕文件不存在、依赖缺失、加载失败。/api/health 会出现
        {"detector": "yolo", "detector_ready": false} 这种自相矛盾的组合，
        而文件名让人误读成"已启用真实模型"。
        """
        if not self.settings.model_path:
            return "mock"
        return "yolo" if self._model is not None else "unavailable"

    def _get_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    model_path = Path(self.settings.model_path)
                    if not model_path.is_file():
                        raise RuntimeError("MODEL_PATH does not point to a model file")
                    config_dir = self.settings.result_dir / ".ultralytics"
                    config_dir.mkdir(parents=True, exist_ok=True)
                    os.environ.setdefault("YOLO_CONFIG_DIR", str(config_dir.resolve()))
                    os.environ.setdefault("MPLCONFIGDIR", str(config_dir.resolve()))
                    from ultralytics import YOLO

                    self._model = YOLO(str(model_path))
        return self._model

    def warmup(self) -> float:
        """启动时用一张占位图把模型跑热，返回耗时秒数（不可用时返回 0）。

        不预热的话，部署/重启后的**第一次**检测要在请求里现场加载 YOLO 权重、
        初始化 CUDA/线程池、跑 ultralytics 内部 warmup —— 低配 ECS 上这一步
        能到数秒甚至十几秒。而评委演示的第一个动作恰好就是第一次上传，
        等于把最难看的延迟留给了最重要的时刻。这里挪到 lifespan 里做掉。
        """
        if not self.settings.model_path:
            return 0.0
        import time

        started = time.perf_counter()
        try:
            # 用 640x640 灰底占位图：够触发一次完整的 forward + NMS，
            # 又不至于因为图片内容产生多余开销
            dummy = np.zeros((640, 640, 3), dtype=np.uint8)
            dummy[:] = (128, 128, 128)
            with self._infer_lock:
                self._get_model().predict(
                    source=dummy, conf=self.settings.conf_threshold, verbose=False
                )
        except Exception as exc:  # noqa: BLE001
            # 预热失败不能拦住启动：模型文件坏了应该由真实请求报错，
            # 而不是让服务起不来（那样连登录页都打不开，更难排查）
            logger.warning("detector warmup skipped: %s: %s", exc.__class__.__name__, exc)
            return 0.0
        return time.perf_counter() - started

    def _to_predictions(self, results) -> list[dict[str, Any]]:
        """把 Ultralytics 结果转成统一的结构化格式（图片与视频抽帧共用）。"""
        predictions: list[dict[str, Any]] = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = (round(float(v), 2) for v in box.xyxy[0])
                class_name = result.names[int(box.cls)]
                predictions.append(
                    {
                        "class": class_name,
                        # 中文虫种名，便于前端与报告直接展示（未收录则回退英文）
                        "class_cn": to_chinese(class_name),
                        "confidence": round(float(box.conf), 4),
                        "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                    }
                )
        return predictions

    # ── 全图 + 局部切片 TTA ────────────────────────────────────────────
    def _gather(self, bgr, scales: tuple[int, ...], tiles: int, conf: float):
        """全图按给定尺度推理，再把图切成 tiles×tiles 块各推理一次，收集候选框。

        切片单独推理的意义：整图缩到 640 时，毫米级螨虫只剩几个像素，
        模型只能按形状猜成蚜虫；切成四块后每块仍是 640，目标保持原始
        像素尺寸，形态特征才留得住。

        返回 [(cls_id, conf, (x1,y1,x2,y2)), ...]，坐标一律映射回原图。
        """
        raw = []
        for s in scales:
            results = self._get_model().predict(source=bgr, conf=conf, imgsz=s, verbose=False)
            for result in results:
                for box in result.boxes:
                    raw.append((int(box.cls), float(box.conf),
                                tuple(float(v) for v in box.xyxy[0])))

        if not tiles:
            return raw

        h, w = bgr.shape[:2]
        step_h, step_w = h / tiles, w / tiles
        oh, ow = step_h * TILE_OVERLAP, step_w * TILE_OVERLAP
        for r in range(tiles):
            for c in range(tiles):
                y1 = max(0, int(r * step_h - oh))
                y2 = min(h, int((r + 1) * step_h + oh))
                x1 = max(0, int(c * step_w - ow))
                x2 = min(w, int((c + 1) * step_w + ow))
                crop = bgr[y1:y2, x1:x2]
                if crop.size == 0:
                    continue
                results = self._get_model().predict(
                    source=crop, conf=conf, imgsz=640, verbose=False)
                for result in results:
                    for box in result.boxes:
                        x, y, xb, yb = (float(v) for v in box.xyxy[0])
                        raw.append((int(box.cls), float(box.conf),
                                    (x + x1, y + y1, xb + x1, yb + y1)))
        return raw

    @staticmethod
    def _cluster_bonus(items, size) -> float:
        """同类框的空间聚集度（0~1）。真害虫常常成片出现，孤立噪声框不该被当成主要害虫。"""
        return _cluster_bonus(items, size)

    def _aggregate(self, raw, size) -> list[tuple]:
        """空间聚类 → 簇内类别投票 → 置信度过滤 → 按『类别置信度之和 × 聚集度加成』排序。

        返回 [(cls_id, conf, (x1,y1,x2,y2)), ...]，与 predict_image 的解包一致。

        四步的顺序是有讲究的，别调换：

        1) **空间聚类**（_cluster_individuals）—— 与类别无关地把候选框归成个体簇。
           这一步放在类别判定之前是整个修复的核心：旧结构先按类别分组，
           同一只虫的不同类别候选分在不同组、各自留一个框，于是界面显示「×2」
           且一只虫被报成两个虫种。先聚类就把「一只虫」定义成了几何概念，
           后面无论怎么投票都只会产出一个框。

        2) **簇内类别投票** —— 每簇取置信度最高的那个候选作为代表框，
           它的类别就是这只虫的虫种。用「最高置信度」而不是各类别置信度求和：
           求和会让候选碎片多的类别虚高（一个类别被5 个切片各认一次，
           每次 0.2，加起来 1.0 就能压过单次 0.6 的正确类别）。
           实测求和投票反而把 Top-1 从 87 拉到 82。

        3) **置信度过滤** —— 看的是**簇内最高置信度**，不是代表框的置信度。
           两者在投票=max 时相等，但语义不同：这只虫存不存在，由最强的那份
           证据决定。若按「投票选中类别的最高置信度」过滤，一个 0.55 的虫
           里若混进0.29 的另一类别，整个簇会被丢掉，漏检从 18 张涨到 23 张。

        4) **排序** —— 按类别聚合打分（该类所有框置信度求和 × 聚集度加成），
           与前端「主要害虫优先展示」的预期一致。这段逻辑与聚类无关，未改动。
        """
        s = self.settings

        # 1) + 2) 空间聚类，每簇选一个代表框（类别由它决定）
        keep: list[tuple] = []
        for cluster in _cluster_individuals(raw):
            # 3) 置信度过滤：看簇内最强证据
            if max(b[1] for b in cluster) < s.detect_min_conf:
                continue
            keep.append(max(cluster, key=lambda b: b[1]))

        # 4) 按类别聚合打分（保持原有逻辑，输出顺序与前端兼容）
        by_cls: dict[int, list[tuple]] = defaultdict(list)
        for b in keep:
            by_cls[b[0]].append(b)

        scored = []
        for cls, items in by_cls.items():
            best = max(b[1] for b in items)
            if best < s.detect_min_conf:
                continue
            score = sum(b[1] for b in items)
            if s.detect_cluster_bonus:
                score *= 1 + s.detect_cluster_bonus * self._cluster_bonus(items, size)
            scored.append((score, best, cls))
        scored.sort(key=lambda x: (-x[0], -x[1]))

        # 5) 按原有顺序输出（保持与 predict_image 的解包一致）
        out: list[tuple] = []
        for _, _, cls in scored:
            out.extend(sorted(by_cls[cls], key=lambda b: -b[1]))
        return out

    def predict_frame(self, frame_bgr) -> list[dict[str, Any]]:
        """视频抽帧检测：只要结构化结果，不生成标注图。

        与 predict_image 的区别：predict_image 需要把带框结果图落盘给用户回看，
        而视频的中间帧标注图生成后立刻被丢弃——实测落盘 28ms/帧，占单帧耗时 36%，
        纯属浪费。边界框由 render_video 直接画在写入输出视频的帧上。
        """
        if not self.settings.model_path:
            if not self.settings.allow_mock_detector:
                raise RuntimeError("No YOLO model configured")
            return []
        with self._infer_lock:
            results = self._get_model().predict(
                source=frame_bgr, conf=self.settings.conf_threshold, verbose=False
            )
        return self._to_predictions(results)

    def predict_image(
        self,
        content: bytes,
        output: Path,
        rgb: "np.ndarray | None" = None,
    ) -> list[dict[str, Any]]:
        """图片检测并落盘标注图。

        rgb 是调用方已经解码好的 RGB 数组（files.read_image 顺带产出）。
        传了就直接用，省掉一次整图解码 + RGB 转换；
        没传（老调用方/脚本）则退回自己解码。
        """
        if not self.settings.model_path:
            if not self.settings.allow_mock_detector:
                raise RuntimeError("No YOLO model configured")
            image = Image.open(io.BytesIO(content)).convert("RGB")
            draw = ImageDraw.Draw(image)
            draw.rectangle((2, 2, image.width - 3, image.height - 3), outline="#22c55e", width=3)
            draw.text((12, 12), "Demo mode - configure MODEL_PATH", fill="#22c55e")
            image.save(output, "JPEG", quality=90)
            return []

        if rgb is None:
            rgb = np.asarray(Image.open(io.BytesIO(content)).convert("RGB"))
        # RGB->BGR：ultralytics 把 ndarray 输入当 BGR 解释
        source = rgb[..., ::-1]

        s = self.settings
        if s.detect_tta:
            scales = tuple(int(x) for x in s.detect_scales.split(",") if x.strip())
            with self._infer_lock:
                raw = self._gather(source, scales or (640,), max(0, s.detect_tiles),
                                   s.detect_gather_conf)
            ranked = self._aggregate(raw, source.shape[:2])
            names = self._get_model().names
            # 主结论 = 全局最高置信度那一类；其余接近它的类别标为「疑似同种」，
            # 理由与阈值见 _is_suspect_alternative 的注释。
            best_conf = max((c for _, c, _ in ranked), default=0.0)
            predictions = []
            for cls, conf, box in ranked:
                cn = to_chinese(names[cls])
                predictions.append(
                    {
                        "class": names[cls],
                        "class_cn": cn,
                        "confidence": round(conf, 4),
                        # primary  = 界面上作为结论展示的虫种
                        # suspect  = 同一批虫的低置信度变体，前端折叠成「疑似」
                        "is_primary": conf >= best_conf,
                        "is_suspect": (conf < best_conf
                                       and _is_suspect_alternative(conf, best_conf)),
                        "bbox": {"x1": round(box[0], 2), "y1": round(box[1], 2),
                                 "x2": round(box[2], 2), "y2": round(box[3], 2)},
                    }
                )
            # 多尺度结果来自多次推理，没有单个 result 可以 plot()，
            # 聚合完自己画（draw_labels 支持中文，且只做一次色彩空间往返）
            plotted = draw_labels(source.copy(), predictions)
            Image.fromarray(plotted[..., ::-1]).save(output, "JPEG", quality=90)
            return predictions

        with self._infer_lock:
            results = self._get_model().predict(source=source, conf=self.settings.conf_threshold, verbose=False)
        plotted_saved = False
        for result in results:
            plotted = result.plot()
            Image.fromarray(plotted[..., ::-1]).save(output, "JPEG", quality=90)
            plotted_saved = True
        predictions = self._to_predictions(results)
        # 零检出时 result.plot() 不会执行，直接把原图落盘，保证 result_path 始终有对应文件
        if not plotted_saved:
            Image.open(io.BytesIO(content)).convert("RGB").save(output, "JPEG", quality=90)
        return predictions


detector = Detector()
