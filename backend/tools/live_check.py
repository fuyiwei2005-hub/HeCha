# -*- coding: utf-8 -*-
"""用真实模型 + 真实图片跑一遍当前生产代码，核对离线 A/B 的结论。

背景：离线重放旧逻辑在稻纵卷叶螟_04.jpg 上得到 3 个框，但用户截图上是 4 个框
（稻纵卷叶螟×2、叶蝉×2，且出现了 78% 这个置信度 —— 而导出的候选框里最高只有
0.6382）。说明「用户上传的那张图」与「资产里那张图」或「当时的代码」不是同一份。
必须用真实链路核对，否则离线 A/B 的结论会答非所问。

输出：_live_out.txt
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CANDIDATES = [
    Path(r"D:\pestguard\_外部验证集\网图人工复核\稻纵卷叶螟_04.jpg"),
    Path(r"D:\pestguard\_队友交图_待检\PestGuard 图片\稻纵卷叶螟_04.jpg"),
]


def main() -> int:
    L: list[str] = []

    L.append("【步骤1】两张同名图是否同一份文件")
    for p in CANDIDATES:
        if p.is_file():
            h = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
            L.append(f"  {p}  {p.stat().st_size} bytes  sha1={h}")
        else:
            L.append(f"  {p}  [不存在]")

    L.append("\n【步骤2】真实模型跑当前生产代码")
    from app.core.config import get_settings
    from app.services.detector import detector

    s = get_settings()
    L.append(f"  MODEL_PATH={s.model_path}")
    L.append(f"  detect_tta={s.detect_tta} scales={s.detect_scales} "
             f"tiles={s.detect_tiles} gather_conf={s.detect_gather_conf} "
             f"min_conf={s.detect_min_conf} cluster_bonus={s.detect_cluster_bonus}")
    L.append(f"  detector.mode={detector.mode}")

    tmp = Path(tempfile.gettempdir()) / "pg_live_out.jpg"
    for p in CANDIDATES:
        if not p.is_file():
            continue
        try:
            detector.predict_image(p.read_bytes(), tmp)
        except Exception as exc:  # noqa: BLE001
            L.append(f"  {p.name}: 推理失败 {exc.__class__.__name__}: {exc}")
            continue
        # 再跑一次拿原始候选
        from PIL import Image
        import numpy as np
        rgb = np.asarray(Image.open(p).convert("RGB"))
        with detector._infer_lock:
            raw = detector._gather(rgb[..., ::-1], (640,), s.detect_tiles,
                                   s.detect_gather_conf)
        L.append(f"\n  ── {p.parent.name}/{p.name}  {rgb.shape[1]}x{rgb.shape[0]}")
        L.append(f"     原始候选 {len(raw)} 个：")
        for cls, conf, bx in sorted(raw, key=lambda x: -x[1]):
            L.append(f"       {detector._get_model().names[cls]:<32}{conf:.4f} "
                     f"[{bx[0]:.1f},{bx[1]:.1f},{bx[2]:.1f},{bx[3]:.1f}]")
        out = detector._aggregate(raw, rgb.shape[:2])
        L.append(f"     _aggregate 返回 {len(out)} 个（元素结构 {len(out[0]) if out else 0} 元组）")
        from app.services.pest_names import to_chinese
        for cls, conf, bx in out:
            L.append(f"       {to_chinese(detector._get_model().names[cls]):<12}{conf:.4f} "
                     f"[{bx[0]:.1f},{bx[1]:.1f},{bx[2]:.1f},{bx[3]:.1f}]")
        preds = detector.predict_image(p.read_bytes(), tmp)
        from collections import Counter
        cnt = Counter(x["class_cn"] for x in preds)
        L.append(f"     predict_image 输出 {len(preds)} 个；按虫种计数 = {dict(cnt)}")

    (ROOT / "_live_out.txt").write_text("\n".join(L), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())