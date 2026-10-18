"""
模型评估脚本 —— 补齐参赛必需的模型性能指标。

背景
-----
仓库里只有一个 best.pt，没有任何评估脚本、没有 mAP 数据。评委几乎必然追问
"准确率多少、数据哪来的、是你自己训的吗"，没有数字就无法作答。
本脚本用真实验证集跑出 mAP50 / mAP50-95 / 各类别 AP / 推理速度，
并同时导出 JSON 与 Markdown，可直接贴进软件设计文档。

用法
-----
务必在 backend 目录下执行（项目自带定制 ultralytics 运行时，不能用官方包）：

    cd backend
    .venv\\Scripts\\python.exe tools\\evaluate.py --data <数据集yaml> --split val

常用参数
--------
    --data       数据集 yaml 路径（必填，例如 F:\\YOLO12\\rice-pets\\rice-pets.yaml）
    --model      权重路径，默认 ../model_weights/best.pt
    --split      val / test，默认 val
    --imgsz      输入尺寸，默认 640（与训练一致）
    --conf       置信度阈值，默认 0.4（与线上 conf_threshold 一致，便于口径对齐）
    --out        结果输出目录，默认 ../docs

产出
-----
    docs/model_metrics.json    结构化指标
    docs/model_metrics.md      Markdown 表格（可直接复制进设计文档）
    runs/detect/val*/          混淆矩阵、PR 曲线等图（Ultralytics 自动生成）

注意
-----
本脚本不训练、不修改任何现有代码，只做只读评估。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 保证能 import 到项目自带的定制 ultralytics（backend/ultralytics）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fmt(v, nd=4):
    """安全格式化浮点数。"""
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


def run_eval(model_path: str, data_yaml: str, split: str, imgsz: int,
             conf: float, out_dir: Path) -> dict:
    from ultralytics import YOLO

    print(f"[1/3] 加载权重: {model_path}")
    model = YOLO(model_path)
    names = model.names
    print(f"      类别数: {len(names)}")

    print(f"[2/3] 在 {split} 集上评估（imgsz={imgsz}, conf={conf}）…")
    res = model.val(data=data_yaml, split=split, imgsz=imgsz, conf=conf,
                    plots=True, verbose=False)

    box = getattr(res, "box", None)
    if box is None:
        raise RuntimeError("评估未返回 box 指标，请检查数据集 yaml 与权重是否匹配。")

    # 各类别 AP（maps 与 names 顺序一致）
    maps = list(getattr(box, "maps", None) or [])
    per_class = []
    for i in sorted(names):
        ap50_95 = maps[i] if i < len(maps) else None
        per_class.append({
            "id": int(i),
            "class": str(names[i]),
            "ap50_95": _fmt(ap50_95),
        })
    per_class.sort(key=lambda d: (d["ap50_95"] is None, -(d["ap50_95"] or 0)))

    speed = getattr(res, "speed", {}) or {}

    metrics = {
        "model": str(Path(model_path).resolve()),
        "data": str(data_yaml),
        "split": split,
        "imgsz": imgsz,
        "conf": conf,
        "num_classes": len(names),
        "mAP50": _fmt(getattr(box, "map50", None)),
        "mAP50_95": _fmt(getattr(box, "map", None)),
        "mAP75": _fmt(getattr(box, "map75", None)),
        "precision": _fmt(getattr(box, "mp", None)),
        "recall": _fmt(getattr(box, "mr", None)),
        "fitness": _fmt(getattr(res, "fitness", None)),
        "speed_ms": {
            "preprocess": _fmt(speed.get("preprocess"), 2),
            "inference": _fmt(speed.get("inference"), 2),
            "postprocess": _fmt(speed.get("postprocess"), 2),
        },
        "per_class": per_class,
    }

    print("[3/3] 写出结果…")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "model_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "model_metrics.md").write_text(
        to_markdown(metrics), encoding="utf-8")

    return metrics


def to_markdown(m: dict) -> str:
    lines = [
        "# 模型评估报告",
        "",
        f"- 权重：`{m['model']}`",
        f"- 数据集：`{m['data']}`（{m['split']} 集）",
        f"- 输入尺寸：{m['imgsz']} · 置信度阈值：{m['conf']} · 类别数：{m['num_classes']}",
        "",
        "## 总体指标",
        "",
        "| 指标 | 数值 |",
        "| --- | --- |",
        f"| mAP@0.5 | {m['mAP50']} |",
        f"| mAP@0.5:0.95 | {m['mAP50_95']} |",
        f"| mAP@0.75 | {m['mAP75']} |",
        f"| Precision | {m['precision']} |",
        f"| Recall | {m['recall']} |",
    ]
    if m["speed_ms"].get("inference"):
        s = m["speed_ms"]
        lines += [
            f"| 单张推理耗时 | {s['inference']} ms（预处理 {s['preprocess']} ms / "
            f"后处理 {s['postprocess']} ms） |",
        ]
    lines += ["", "## 各类别 AP@0.5:0.95", "", "| 排名 | 类别 | AP |", "| --- | --- | --- |"]
    for i, c in enumerate(m["per_class"], 1):
        v = c["ap50_95"]
        lines.append(f"| {i} | {c['class']} | {v if v is not None else '—'} |")
    lines += ["", "> 由 `backend/tools/evaluate.py` 自动生成。", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="评估 best.pt 并导出参赛用指标")
    ap.add_argument("--data", required=True, help="数据集 yaml 路径")
    ap.add_argument("--model", default="../model_weights/best.pt")
    ap.add_argument("--split", default="val", choices=["val", "test"])
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--conf", type=float, default=0.4)
    ap.add_argument("--out", default="../docs")
    a = ap.parse_args()

    if not Path(a.model).exists():
        sys.exit(f"权重不存在：{a.model}")
    if not Path(a.data).exists():
        sys.exit(
            f"数据集 yaml 不存在：{a.data}\n"
            "本仓库不含训练数据集。请从训练该权重的机器（见 README「模型溯源」）\n"
            "拷贝 rice-pets 数据集与其 yaml 后重试；若确实拿不到，参见\n"
            "docs/参赛冲刺清单.md 的「方案 B：自建小测试集」。"
        )

    m = run_eval(a.model, a.data, a.split, a.imgsz, a.conf, Path(a.out))
    print()
    print("=" * 46)
    print(f"  mAP@0.5        : {m['mAP50']}")
    print(f"  mAP@0.5:0.95   : {m['mAP50_95']}")
    print(f"  Precision      : {m['precision']}")
    print(f"  Recall         : {m['recall']}")
    print(f"  推理耗时       : {m['speed_ms'].get('inference')} ms/张")
    print("=" * 46)
    print(f"已写出：{Path(a.out).resolve() / 'model_metrics.md'}")


if __name__ == "__main__":
    main()
