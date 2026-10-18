"""
性能基准测试 —— 不训练模型、不部署上云也能产出的系统级指标。

背景
-----
很多团队以为"没有测试集就没有数据可写"，其实不然。模型精度（mAP）依赖标注集，
但**系统性能指标完全自己能测**：推理延迟、吞吐、模型体积、参数量、阈值敏感性、
视频处理速度……这些恰恰是应用类赛道看重的工程能力证据，且今天就能拿到。

本脚本不训练、不联网、不改动任何现有代码，只读跑推理并统计。

用法
-----
务必在 backend 目录下执行（依赖项目自带的定制 ultralytics 运行时）：

    cd backend
    .venv\\Scripts\\python.exe tools\\benchmark.py

可选参数
--------
    --imgs      测试图片路径，可多次传入；默认取仓库根目录的测试图
    --video     测试视频路径，默认 测试_虫子_2秒.mp4
    --repeat    每张图重复推理次数（取均值），默认 5
    --confs     置信度阈值扫描列表，默认 0.25 0.4 0.5 0.6
    --out       结果输出目录，默认 ../docs

产出
-----
    docs/benchmark.json
    docs/benchmark.md     可直接复制进软件设计文档的「性能测试」章节
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IMGS = [
    ROOT / "测试_蚜虫.jpg",
    ROOT / "测试_红蜘蛛.jpg",
    ROOT / "测试_玉米螟.jpg",
    ROOT / "测试_斜纹夜蛾.jpg",
]
DEFAULT_VIDEO = ROOT / "测试_虫子_2秒.mp4"


def load_model(model_path: str):
    from ultralytics import YOLO
    t0 = time.perf_counter()
    model = YOLO(model_path)
    load_s = time.perf_counter() - t0
    return model, load_s


def model_stats(model, weight_path: Path) -> dict:
    """统计参数量 / 体积 / 计算量（尽力而为，缺能力不报错）。"""
    stats: dict = {}
    try:
        params = sum(p.numel() for p in model.model.parameters())
        stats["params_M"] = round(params / 1e6, 3)
    except Exception:
        pass
    try:
        stats["size_MB"] = round(weight_path.stat().st_size / 1024 / 1024, 2)
    except Exception:
        pass
    try:
        # ultralytics 自带 FLOPs 估算（按 640 输入）
        stats["gflops"] = round(model.get_flops() / 1e9, 2) if hasattr(model, "get_flops") else None
    except Exception:
        stats["gflops"] = None
    return stats


def warmup(model, img, n=2):
    for _ in range(n):
        model.predict(source=img, conf=0.4, verbose=False)


def bench_one(model, img, conf: float, repeat: int) -> dict:
    """对单张图重复推理，返回耗时统计与检出数。"""
    lat, n_det = [], 0
    speed = {}
    for i in range(repeat):
        t0 = time.perf_counter()
        res = model.predict(source=img, conf=conf, verbose=False)
        lat.append((time.perf_counter() - t0) * 1000)
        if i == 0:
            n_det = len(res[0].boxes) if res and res[0].boxes is not None else 0
            try:
                speed = dict(res[0].speed or {})
            except Exception:
                speed = {}
    return {
        "detections": int(n_det),
        "latency_ms_mean": round(statistics.mean(lat), 1),
        "latency_ms_min": round(min(lat), 1),
        "latency_ms_max": round(max(lat), 1),
        "stage_ms": {
            "preprocess": round(speed.get("preprocess", 0), 1),
            "inference": round(speed.get("inference", 0), 1),
            "postprocess": round(speed.get("postprocess", 0), 1),
        },
    }


def read_images(paths: list[Path]):
    """把图片读成与线上一致的 BGR ndarray（见 detector.predict_image）。"""
    import numpy as np
    from PIL import Image
    out = []
    for p in paths:
        if not p.exists():
            print(f"  [跳过] 不存在: {p}")
            continue
        arr = Image.open(p).convert("RGB")
        out.append((p.name, (arr.size[0], arr.size[1]),
                    np.asarray(arr)[..., ::-1]))
    return out


def bench_video(model, video_path: Path, conf: float) -> dict | None:
    """逐帧跑视频，测吞吐。"""
    if not video_path.exists():
        print(f"  [跳过] 视频不存在: {video_path}")
        return None
    try:
        import cv2
    except ImportError:
        print("  [跳过] 未安装 opencv，跳过视频测试")
        return None

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"  [跳过] 无法打开视频: {video_path}")
        return None

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 0
    frames, lat = 0, []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t0 = time.perf_counter()
        model.predict(source=frame, conf=conf, verbose=False)
        lat.append((time.perf_counter() - t0) * 1000)
        frames += 1
    cap.release()

    if not frames:
        return None
    mean_ms = statistics.mean(lat)
    return {
        "frames": frames,
        "source_fps": round(src_fps, 2) if src_fps else None,
        "ms_per_frame_mean": round(mean_ms, 1),
        "throughput_fps": round(1000 / mean_ms, 2) if mean_ms else None,
        "duration_s": round(src_fps and total / src_fps or 0, 2),
    }


def conf_sweep(model, imgs, confs: list[float]) -> dict:
    """阈值敏感性：同一批图在不同 conf 下的总检出数——体现"阈值可调"的工程取舍。"""
    out = {}
    for c in confs:
        total = 0
        for _, _, arr in imgs:
            res = model.predict(source=arr, conf=c, verbose=False)
            total += len(res[0].boxes) if res and res[0].boxes is not None else 0
        out[f"{c:.2f}"] = total
    return out


def to_markdown(r: dict) -> str:
    L = ["# 系统性能基准测试", ""]
    L.append(f"- 权重：`{r['model_path']}`")
    L.append(f"- 运行环境：{r['env']['python']} · {r['env']['device']}")
    L.append(f"- 测试时间：{r['timestamp']}")
    L.append("")

    s = r["model_stats"]
    L += ["## 模型规模", "", "| 指标 | 数值 |", "| --- | --- |"]
    if s.get("params_M") is not None:
        L.append(f"| 参数量 | {s['params_M']} M |")
    if s.get("size_MB") is not None:
        L.append(f"| 权重体积 | {s['size_MB']} MB |")
    if s.get("gflops") is not None:
        L.append(f"| 计算量 | {s['gflops']} GFLOPs @640 |")
    L.append(f"| 模型加载耗时 | {r['load_s']} s |")
    L.append("")

    L += ["## 单图推理延迟（含预处理与后处理）", "",
          "| 测试图 | 分辨率 | 检出数 | 平均耗时 | 最快 | 最慢 | 吞吐 |",
          "| --- | --- | --- | --- | --- | --- | --- |"]
    for name, d in r["images"].items():
        w, h = d["resolution"]
        fps = round(1000 / d["latency_ms_mean"], 2) if d["latency_ms_mean"] else "—"
        L.append(f"| {name} | {w}×{h} | {d['detections']} | "
                 f"{d['latency_ms_mean']} ms | {d['latency_ms_min']} ms | "
                 f"{d['latency_ms_max']} ms | {fps} FPS |")
    if r.get("stage_ms_avg"):
        st = r["stage_ms_avg"]
        L.append("")
        L.append(f"阶段均值：预处理 {st['preprocess']} ms · "
                 f"推理 {st['inference']} ms · 后处理 {st['postprocess']} ms")
    L.append("")

    if r.get("conf_sweep"):
        L += ["## 置信度阈值敏感性", "", "| conf | 4 张测试图总检出数 |", "| --- | --- |"]
        for c, n in r["conf_sweep"].items():
            L.append(f"| {c} | {n} |")
        L.append("")

    if r.get("video"):
        v = r["video"]
        L += ["## 视频处理吞吐", "", "| 指标 | 数值 |", "| --- | --- |"]
        L.append(f"| 测试视频 | {v['frames']} 帧 |")
        if v.get("source_fps"):
            L.append(f"| 源视频帧率 | {v['source_fps']} FPS |")
        L.append(f"| 单帧处理耗时 | {v['ms_per_frame_mean']} ms |")
        L.append(f"| 处理吞吐 | {v['throughput_fps']} FPS |")
        L.append("")

    L += ["> 由 `backend/tools/benchmark.py` 自动生成。数据为本地 CPU 实测，",
          "> 不同硬件结果会有差异，报告中应注明测试环境。", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="系统性能基准测试")
    ap.add_argument("--model", default="../model_weights/best.pt")
    ap.add_argument("--imgs", nargs="*", default=[str(p) for p in DEFAULT_IMGS])
    ap.add_argument("--video", default=str(DEFAULT_VIDEO))
    ap.add_argument("--repeat", type=int, default=5)
    ap.add_argument("--confs", nargs="*", type=float, default=[0.25, 0.4, 0.5, 0.6])
    ap.add_argument("--out", default="../docs")
    a = ap.parse_args()

    weight = Path(a.model)
    if not weight.exists():
        sys.exit(f"权重不存在：{weight}")

    import platform
    from datetime import datetime

    print(f"[1/5] 加载模型 {weight} …")
    model, load_s = load_model(str(weight))
    print(f"      加载耗时 {load_s:.2f}s")

    print("[2/5] 统计模型规模 …")
    stats = model_stats(model, weight)
    print(f"      {stats}")

    imgs = read_images([Path(p) for p in a.imgs])
    if not imgs:
        sys.exit("没有可用的测试图片。")
    print(f"[3/5] 预热并测试 {len(imgs)} 张图 × {a.repeat} 次 …")

    name0, _, arr0 = imgs[0]
    warmup(model, arr0)

    results, stages = {}, {"preprocess": [], "inference": [], "postprocess": []}
    for name, size, arr in imgs:
        d = bench_one(model, arr, 0.4, a.repeat)
        results[name] = {"resolution": size, **d}
        for k in stages:
            stages[k].append(d["stage_ms"][k])
        print(f"      {name:<20} 检出 {d['detections']:>2} · {d['latency_ms_mean']:>7.1f} ms")

    print(f"[4/5] 阈值扫描 {a.confs} …")
    sweep = conf_sweep(model, imgs, a.confs)
    print(f"      {sweep}")

    print("[5/5] 视频吞吐测试 …")
    vid = bench_video(model, Path(a.video), 0.4)

    report = {
        "model_path": str(weight.resolve()),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "env": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "device": "CPU",
        },
        "load_s": round(load_s, 2),
        "model_stats": stats,
        "repeat": a.repeat,
        "images": results,
        "stage_ms_avg": {k: round(statistics.mean(v), 1) for k, v in stages.items() if v},
        "conf_sweep": sweep,
        "video": vid,
    }

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "benchmark.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "benchmark.md").write_text(to_markdown(report), encoding="utf-8")

    print()
    print("=" * 50)
    print(f"  平均推理延迟 : {report['stage_ms_avg'].get('inference')} ms/张")
    print(f"  处理吞吐     : {round(1000 / statistics.mean([v['latency_ms_mean'] for v in results.values()]), 2)} FPS")
    print(f"  模型体积     : {stats.get('size_MB')} MB / {stats.get('params_M')} M 参数")
    if vid:
        print(f"  视频吞吐     : {vid['throughput_fps']} FPS")
    print("=" * 50)
    print(f"已写出：{(out / 'benchmark.md').resolve()}")


if __name__ == "__main__":
    main()
