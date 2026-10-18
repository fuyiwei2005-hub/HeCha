"""从 best.pt 里解出训练资产，产出：
  1. backend/model_weights/training_metrics.json —— 完整指标存档
  2. backend/model_weights/training_curve.png    —— PPT 用的训练曲线

权重里保存了 89 个 epoch 的 loss / precision / recall / mAP 原始序列，
原训练目录 F:\\YOLO12\\rice-pets 已丢失，这是唯一还能拿到真实训练过程的地方。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
WEIGHT = ROOT.parent / "model_weights" / "best.pt"

# 项目自带 ultralytics 副本在 backend/ 下，反序列化 pt 需要它能被 import
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ck = torch.load(WEIGHT, map_location="cpu", weights_only=False)
    results = ck["train_results"]
    metrics = ck["train_metrics"]
    args = ck["train_args"]

    summary = {
        "model_architecture": str(args.get("model", "")).rsplit("\\", 1)[-1],
        "dataset_yaml": str(args.get("data", "")),
        "dataset_available": False,  # 原目录已丢失，见下方说明
        "epochs_configured": args.get("epochs"),
        "best_epoch": ck.get("epoch"),
        "imgsz": args.get("imgsz"),
        "batch": args.get("batch"),
        "train_date": ck.get("date"),
        "ultralytics_version": ck.get("version"),
        "precision": metrics.get("metrics/precision(B)"),
        "recall": metrics.get("metrics/recall(B)"),
        "mAP50": metrics.get("metrics/mAP50(B)"),
        "mAP50_95": metrics.get("metrics/mAP50-95(B)"),
        "fitness": metrics.get("fitness"),
        "val_box_loss": metrics.get("val/box_loss"),
        "val_cls_loss": metrics.get("val/cls_loss"),
        "val_dfl_loss": metrics.get("val/dfl_loss"),
    }

    out_dir = WEIGHT.parent
    (out_dir / "training_metrics.json").write_text(
        json.dumps({"summary": summary, "curves": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("已写出 training_metrics.json")

    # 曲线图
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        ep = results["epoch"]
        fig, axes = plt.subplots(1, 3, figsize=(16, 4.2))

        ax = axes[0]
        ax.plot(ep, results["train/box_loss"], label="box_loss", lw=1.6)
        ax.plot(ep, results["train/cls_loss"], label="cls_loss", lw=1.6)
        ax.plot(ep, results["train/dfl_loss"], label="dfl_loss", lw=1.6)
        ax.set_title("Training Loss", fontsize=12)
        ax.set_xlabel("epoch")
        ax.legend(fontsize=9)
        ax.grid(alpha=0.3)

        ax = axes[1]
        ax.plot(ep, results["val/box_loss"], label="val box", lw=1.6, color="#c0392b")
        ax.plot(ep, results["val/cls_loss"], label="val cls", lw=1.6, color="#2980b9")
        ax.plot(ep, results["val/dfl_loss"], label="val dfl", lw=1.6, color="#27ae60")
        ax.set_title("Validation Loss", fontsize=12)
        ax.set_xlabel("epoch")
        ax.legend(fontsize=9)
        ax.grid(alpha=0.3)

        ax = axes[2]
        ax.plot(ep, results["metrics/precision(B)"], label="Precision", lw=1.8)
        ax.plot(ep, results["metrics/recall(B)"], label="Recall", lw=1.8)
        ax.plot(ep, results["metrics/mAP50(B)"], label="mAP@0.5", lw=1.8)
        ax.plot(ep, results["metrics/mAP50-95(B)"], label="mAP@0.5:0.95", lw=1.8)
        ax.set_title("Precision / Recall / mAP", fontsize=12)
        ax.set_xlabel("epoch")
        ax.legend(fontsize=9)
        ax.grid(alpha=0.3)

        best = ck.get("epoch")
        if best:
            for a in axes:
                a.axvline(best, ls="--", color="#888", lw=1)
        fig.suptitle(
            f"PestGuard Detector Training  |  best epoch {best}  |  "
            f"mAP@0.5 = {summary['mAP50']:.4f}",
            fontsize=13,
        )
        fig.tight_layout()
        fig.savefig(out_dir / "training_curve.png", dpi=160, bbox_inches="tight")
        print("已写出 training_curve.png")
    except Exception as exc:  # noqa: BLE001
        print(f"绘图失败（不影响 JSON）：{exc}")

    print()
    print("=== 关键指标（可直接写进 PPT）===")
    print(f"  Precision   : {summary['precision']:.4f}  ({summary['precision']*100:.2f}%)")
    print(f"  Recall      : {summary['recall']:.4f}  ({summary['recall']*100:.2f}%)")
    print(f"  mAP@0.5     : {summary['mAP50']:.4f}  ({summary['mAP50']*100:.2f}%)")
    print(f"  mAP@0.5:.95 : {summary['mAP50_95']:.4f}  ({summary['mAP50_95']*100:.2f}%)")
    print(f"  best epoch  : {summary['best_epoch']} / {summary['epochs_configured']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
