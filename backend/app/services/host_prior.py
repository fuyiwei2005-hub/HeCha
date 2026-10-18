"""寄主先验（Host Prior）—— 用「用户告知的作物」给检测结果做软重排。

核心安全约束（改动前务必读完）
──────────────────────────────
植物/作物信息只做**加权**，绝不**置零**。理由不是保守，是植保领域的代价不对等：

    漏报（有虫说没虫，农户不打药）>> 误报（认错虫种，顶多多看一眼）

所以任何候选即使与作物「完全冲突」，权重也有硬下限 `scoring.floor`（默认 0.5），
永远不可能因为它不像这个作物的虫而从结果里消失。
作物选错的最坏结果，只是排名下降到第二名，用户仍能在候选列表里看到它。

数据来源
────────
全部来自 data/host_prior.json，而该表由 tools/build_host_prior.py
从 data/knowledge/*.json 的 tags 字段自动生成 —— 不手写虫种-作物对应关系。
本模块不含任何硬编码的虫种名或作物名。

校准状态
────────
SCORING 里的 alpha 是**启发式初值，未经过评测校准**。
必须用 tools/eval_top1.py 跑出 baseline 后回来调参，调完才能写进设计文档。
禁止把默认参数下的提升幅度当成结论汇报。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data" / "host_prior.json"

# 与 scoring.floor 配套的权重上限，防止高置信度候选被放大到失真
_MAX_FACTOR = 1.6


@dataclass
class Scoring:
    alpha_strong: float = 0.35
    alpha_related: float = 0.18
    alpha_conflict: float = -0.25
    floor: float = 0.5
    note: str = ""


@dataclass
class RerankResult:
    """重排结果，保留全部原始信息以便回溯与评测。"""

    predictions: list[dict[str, Any]] = field(default_factory=list)
    crop: str | None = None          # 规范化后的 key（写库、虫种映射都用它）
    crop_label: str | None = None    # 面向用户的显示名（李 -> 李子）
    applied: bool = False
    reason: str = ""      # 未生效/降级时的说明，用于前端提示与排查


class HostPrior:
    def __init__(self, data_path: Path = DATA_PATH) -> None:
        self._path = data_path
        self._data: dict[str, Any] | None = None
        self._load_error: str | None = None

    # ── 加载 ──────────────────────────────────────────────────────────
    def _load(self) -> dict[str, Any] | None:
        """懒加载。文件缺失/损坏时不抛异常，只是禁用先验 —— 不能拖垮主链路。"""
        if self._data is not None:
            return self._data
        try:
            self._data = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self._load_error = f"先验表不存在：{self._path}"
        except json.JSONDecodeError as e:
            self._load_error = f"先验表损坏({e})：{self._path}"
        return self._data

    @property
    def load_error(self) -> str | None:
        self._load()
        return self._load_error

    @property
    def available(self) -> bool:
        return self._load() is not None

    @property
    def scoring(self) -> Scoring:
        data = self._load()
        if not data:
            return Scoring()
        s = dict(data.get("scoring", {}))
        return Scoring(
            alpha_strong=float(s.get("alpha_strong", 0.35)),
            alpha_related=float(s.get("alpha_related", 0.18)),
            alpha_conflict=float(s.get("alpha_conflict", -0.25)),
            floor=float(s.get("floor", 0.5)),
            note=str(s.get("note", "")),
        )

    # ── 作物清单（供前端下拉框） ────────────────────────────────────
    def crops(self) -> list[dict[str, Any]]:
        """下拉框数据。

        返回**全部**作物，用 has_prior 区分两类：
        - True  —— 有虫种先验，能参与排序重排
        - False —— 无虫种先验（如番茄），排序不动，但作物名仍会传给大模型，
                   让防治建议的措辞、用药部位、安全间隔期口径贴合该作物

        不按 has_prior 过滤，是因为过滤掉等于告诉种番茄的用户「我们不支持你的地」，
        而这明明是本功能最容易拿到的一分。
        """
        data = self._load()
        if not data:
            return []
        out = []
        for c in data.get("crops", []):
            strong = c.get("strong", [])
            related = c.get("related", [])
            out.append(
                {
                    "key": c["key"],
                    "label": c.get("label") or c["key"],
                    "aliases": list(c.get("aliases", [])),
                    "region": c.get("region", ""),
                    "has_prior": bool(c.get("has_prior")),
                    "strong_count": len(strong),
                    "related_count": len(related),
                }
            )
        return out

    # ── 作物名解析 ────────────────────────────────────────────────────
    def _crop_index(self) -> dict[str, dict[str, Any]]:
        data = self._load() or {}
        return {c["key"]: c for c in data.get("crops", [])}

    def resolve_crop(self, crop: str | None) -> str | None:
        """把用户传入的作物写法归一化为 key。

        接受三种写法，全部返回同一个 key：
            李子 / 李  -> 李      西红柿 -> 番茄      <nothing> -> None
        不认别名会让先验**静默失效**（判为未知作物、什么都不做），
        这比报错更糟 —— 用户以为选了作物，其实功能没生效。
        """
        if not crop:
            return None
        s = str(crop).strip()
        if not s:
            return None
        idx = self._crop_index()
        if s in idx:
            return s
        for c in idx.values():
            if s == c.get("label") or s in (c.get("aliases") or []):
                return str(c["key"])
        return None

    def display_name(self, crop: str | None) -> str:
        """取得面向用户的显示名（LLM 提示、前端文案用；key 仍用于落库）。"""
        if not crop:
            return ""
        idx = self._crop_index()
        c = idx.get(crop) or idx.get(self.resolve_crop(crop) or "")
        if not c:
            return str(crop)
        return str(c.get("label") or crop)

    def known_crop(self, crop: str | None) -> bool:
        """是否在作物清单里（清单外的作物一律不做任何干预）。"""
        return self.resolve_crop(crop) is not None

    # ── 单条判级 ──────────────────────────────────────────────────────
    def level_of(self, pest_cn: str, crop: str | None) -> tuple[str, float]:
        """返回 (层级, alpha)。层级：strong / related / neutral / conflict。"""
        data = self._load()
        crop = self.resolve_crop(crop)
        if not data or not crop:
            return "neutral", 0.0

        pest = data.get("pests", {}).get(pest_cn)
        if pest is None:
            # 先验表没收录 => 不做任何干预，放它原样竞争
            return "neutral", 0.0

        sc = self.scoring
        generality = pest.get("generality")

        # 广谱害虫（蚜虫/蓟马/蛴螬…）在任何作物上都可能出现 => 一律不动
        # 这是防误伤的关键：这类虫占 46 类的 1/3，一旦加权就全是错的
        if generality in ("broad", "unknown"):
            return "neutral", 0.0

        crop_info = next((c for c in data.get("crops", []) if c["key"] == crop), None)
        if crop_info is None:
            return "neutral", 0.0

        # 该作物没有虫种先验（如番茄）=> 我们对「什么虫会危害它」一无所知，
        # 此时把专性害虫判成 conflict 并降权是纯误伤 —— 没有依据的惩罚比分不动更糟。
        if not crop_info.get("has_prior"):
            return "neutral", 0.0

        if pest_cn in crop_info.get("strong", []):
            return "strong", sc.alpha_strong
        if pest_cn in crop_info.get("related", []):
            return "related", sc.alpha_related

        # 有明确寄主却不在这个作物上 => 冲突，降权但不置零
        return "conflict", sc.alpha_conflict

    # ── 重排 ──────────────────────────────────────────────────────────
    def rerank(
        self, predictions: list[dict[str, Any]], crop: str | None
    ) -> RerankResult:
        """按作物先验重排候选。

        不改变检出数量 —— 只改「谁排第一」，检出的东西一条都不会丢。
        confidence 始终保留视觉置信度；ranking_score 仅用于排序，不是概率。
        """
        if not predictions:
            return RerankResult(predictions=[], crop=crop, applied=False, reason="无检出结果")

        key = self.resolve_crop(crop)
        label = self.display_name(key)
        if not crop or not self.available:
            return RerankResult(
                predictions=list(predictions), crop=key, crop_label=label, applied=False,
                reason="未提供作物" if not crop else "先验表不可用",
            )

        if not key:
            return RerankResult(
                predictions=list(predictions), crop=None, crop_label=str(crop), applied=False,
                reason=f"未知作物「{crop}」，先验未生效",
            )

        sc = self.scoring
        out: list[dict[str, Any]] = []
        for p in predictions:
            item = dict(p)
            raw = float(item.get("confidence", 0.0))
            level, alpha = self.level_of(str(item.get("class_cn") or item.get("class") or ""), crop)

            # 硬底线：factor 永远 >= floor，保证候选不会被抹掉
            factor = max(sc.floor, min(_MAX_FACTOR, 1.0 + alpha))

            item["raw_confidence"] = round(raw, 4)
            item["ranking_score"] = round(raw * factor, 4)
            item["prior"] = {
                "level": level,
                "alpha": round(alpha, 3),
                "factor": round(factor, 3),
                "crop": key,
                "crop_label": label,
                "note": {
                    "strong": "该作物典型害虫，排序权重上调",
                    "related": "同类作物可见，轻度上调",
                    "neutral": "广谱害虫或未收录，不做调整",
                    "conflict": "非该作物寄主，已降权但保留（防止漏检）",
                }.get(level, ""),
            }
            out.append(item)

        out.sort(key=lambda x: x["ranking_score"], reverse=True)
        moved = [p.get("class_cn") for p in predictions] != [p.get("class_cn") for p in out]
        return RerankResult(
            predictions=out, crop=key, crop_label=label, applied=True,
            reason="排序发生变化" if moved else "已加权，原排序未变",
        )

    # ── 给大模型的上下文 ─────────────────────────────────────────────
    def hint_for_llm(self, crop: str | None, predictions: list[dict[str, Any]]) -> str:
        """拼一段作物上下文喂给大模型，让防治建议更贴合田间实际。

        即使先验没有改变排序，作物信息对大模型仍然有用（用药部位、安全间隔期口径）。
        """
        if not crop:
            return ""
        # 对大模型用显示名：说「李子」比说「李」更容易让模型稳定理解作物语义，
        # 单字作物名（李/柿）在 prompt 里容易被当成普通汉字读过。
        show = self.display_name(crop) or str(crop)
        top = [p for p in predictions[:3]]
        if not top:
            return f"用户在【{show}】田块拍摄，但本次未检出明确害虫。"

        names = []
        for p in top:
            cn = p.get("class_cn") or p.get("class")
            if cn:
                names.append(str(cn))
        lv = self.level_of(str(top[0].get("class_cn") or ""), crop)

        lines = [f"拍摄作物：{show}"]
        if names:
            lines.append("检出候选：" + "、".join(names))
        if lv[0] == "strong":
            lines.append(f"提示：{names[0]}是{show}的常见害虫，建议围绕该作物的生育期与用药安全间隔期给出方案。")
        elif lv[0] == "related":
            lines.append(f"提示：{names[0]}在同类作物上可见，但非{show}最典型虫种，建议同时提示核对虫体特征。")
        elif lv[0] == "conflict":
            lines.append(
                f"提示：{names[0]}通常不是{show}的主要害虫，可能是邻近地块迁入或寄主判断有误，"
                f"建议提示用户复核虫体特征与作物，不要直接下结论。"
            )
        lines.append("用药建议必须注明安全间隔期，并优先给出非化学防治措施。")
        return "\n".join(lines)


host_prior = HostPrior()
