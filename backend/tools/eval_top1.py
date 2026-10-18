"""端到端 Top-1 命中率实测脚本。

用途
----
补上「mAP 之外」的那个数：拿一批**你明确知道答案**的虫图跑一遍系统，
统计 Top-1 命中率。评委听不懂 mAP，但听得懂「50 张里对了 42 张」。

用法
----
1. 往图集目录丢图（默认 `D:/pestguard/_实测图集`）：

       蚜虫_01.jpg        红蜘蛛_田里拍的.jpg      稻纵卷叶螟_a.jpg

   **文件名里只要包含 46 类虫种名之一，脚本就自动当作真实标签**，
   不需要你做任何标注。

   可以按来源分子目录，**一级子目录名即数据来源标签**：

       田间/蚜虫_01.jpg        标本/玉米螟_01.jpg        公开/柑橘锈螨_01.jpg

   分组 ≥ 2 个时报告会输出「数据来源构成」表。这是必需的：
   田间实拍、标本照、公开精选图的难度完全不同，混在一起报一个数
   等于默认三者难度相同。详见 `docs/参赛材料/给组员的拍摄要求.md`第四节。

2. 运行（必须在 backend 目录下执行，定制 ultralytics 在这里）：

       .\\.venv\\Scripts\\python.exe tools\\eval_top1.py

   可选参数：
       --dir   图集目录
       --conf  置信度阈值（默认取 .env 的 CONF_THRESHOLD）
       --model 权重路径（默认取 .env 的 MODEL_PATH）
       --out   报告输出路径
       --crop  指定统一作物，开启寄主先验 A/B 对照
       --ab    对同一批图跑「无先验 vs 有先验」两次，输出提升幅度

3. 看报告：Markdown 对照表 + CSV 明细 + 混淆统计。

判定口径
--------
- **Top-1 命中**：置信度最高的那个预测 == 真实虫种
- **任意命中**：预测列表里出现过真实虫种（更宽松，用于分析）
- **漏检**：一个框都没出
- **误判**：出了框但 Top-1 不是真实虫种

 Top-1 命中率是主指标，写进答辩材料的就是这个数。

关于 --ab（寄主先验对照）
------------------------
加了作物上下文以后，**必须证明它真的有帮助**，否则就是给系统白添一个故障点。
`--ab --crop 水稻` 会在同一批图上跑两遍，并给出三件事：

1. 命中率变化：`无先验 78% → 有先验 84%`，这个 delta 才是能写进材料的结论
2. **被纠正的样本**：先验把原本认错的救回来了（收益来源）
3. **被改坏的样本**：先验把原本认对的改错了（代价）

第 3 条尤其重要。哪怕只有一两条，也说明 alpha 调得过猛，必须回来调小。
只报收益、不报代价的对照实验，等于没做实验。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # 定制 ultralytics 与 app 包都在 backend 下

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# 递归收集时要排掉的目录：存放推理结果的 results 会混入 jpg，缓存目录同理。
SKIP_DIR_NAMES = {"results", "__pycache__", ".ipynb_checkpoints", "thumbnails"}


def collect_images(img_dir: Path) -> list[Path]:
    """递归收集图集目录下的所有图片。

    必须递归：实际协作时大家习惯按虫种/来源分子目录（如 `田间/蚜虫_01.jpg`），
    用 iterdir 只会看顶层，子目录里的图会被整批忽略且毫无提示。
    """
    out: list[Path] = []
    for p in img_dir.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in IMAGE_EXTS:
            continue
        if p.name.startswith("."):
            continue
        rel_parts = p.relative_to(img_dir).parts[:-1]
        if any(part.startswith(".") or part in SKIP_DIR_NAMES for part in rel_parts):
            continue
        out.append(p)
    return sorted(out)


def group_of(img_dir: Path, p: Path) -> str:
    """图片所在的一级子目录即数据来源分组（田间 / 标本 / 公开图集 …）。

    放在根目录的图统一归入「根目录」。分组成立的前提是大家按来源分子目录，
    规则见 `docs/参赛材料/给组员的拍摄要求.md`。
    """
    parts = p.relative_to(img_dir).parts
    return parts[0] if len(parts) > 1 else "根目录"


def guess_label(stem: str, names: list[str]) -> str | None:
    """从文件名里猜真实虫种，取最长匹配（避免「红蜘蛛」命中「长腿红蜘蛛」）。"""
    best: str | None = None
    for n in names:
        if n in stem and (best is None or len(n) > len(best)):
            best = n
    return best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT.parent / "_实测图集"))
    ap.add_argument("--conf", type=float, default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--out", default=str(ROOT.parent / "docs" / "参赛材料" / "准确率实测报告.md"))
    ap.add_argument("--crop", default=None,
                    help="统一作物（寄主先验输入），如 --crop 水稻")
    ap.add_argument("--crop-from-name", action="store_true",
                    help="从文件名推断作物（文件名需含作物名），忽略 --crop")
    ap.add_argument("--ab", action="store_true",
                    help="输出「无先验 vs 有先验」对照；不指定则只报基线")
    args = ap.parse_args()

    if args.model:
        os.environ["MODEL_PATH"] = args.model
    if args.conf is not None:
        os.environ["CONF_THRESHOLD"] = str(args.conf)

    from app.core.config import get_settings
    from app.services.detector import detector
    from app.services.host_prior import host_prior
    from app.services.pest_names import CLASS_CN

    names = list(CLASS_CN.values())
    crop_keys = [c["key"] for c in host_prior.crops()] if host_prior.available else []
    settings = get_settings()
    if not settings.model_path or not Path(settings.model_path).is_file():
        print("[错误] 未配置有效 MODEL_PATH，会走 mock 检测器，测出来的数没有意义。")
        print("       请在 backend/.env 里设置 MODEL_PATH，或用 --model 传入权重路径。")
        return 2

    if args.crop and crop_keys and args.crop not in crop_keys:
        print(f"[警告] 「{args.crop}」不在作物清单内，先验不会生效。")
        print(f"       可用作物示例：{'、'.join(crop_keys[:15])} …")
    if args.ab and not args.crop and not args.crop_from_name:
        print("[错误] --ab 需要配合 --crop 或 --crop-from-name 才能开启先验。")
        return 2

    img_dir = Path(args.dir)
    if not img_dir.is_dir():
        img_dir.mkdir(parents=True, exist_ok=True)
        (img_dir / "把图片放这里.txt").write_text(
            "把虫图放进本目录，文件名里带上真实虫种名，例如：\n"
            "  蚜虫_01.jpg\n"
            "  红蜘蛛_田里拍的.jpg\n"
            "  稻纵卷叶螟_a.jpg\n\n"
            "然后回到 backend 目录运行：\n"
            "  .\\.venv\\Scripts\\python.exe tools\\eval_top1.py\n",
            encoding="utf-8",
        )
        print(f"[提示] 已创建图集目录：{img_dir}\n       往里丢图后重新运行本脚本。")
        return 1

    files = collect_images(img_dir)
    skipped: list[tuple[str, str]] = []
    usable: list[tuple[Path, str]] = []
    for p in files:
        label = guess_label(p.stem, names)
        if label is None:
            skipped.append((p.name, "文件名里没识别出虫种名"))
        else:
            usable.append((p, label))

    group_counts: dict[str, int] = {}
    for p, _l in usable:
        g = group_of(img_dir, p)
        group_counts[g] = group_counts.get(g, 0) + 1

    if not usable:
        print(f"[提示] {img_dir} 里没有可用图片。")
        print("       文件名需包含 46 类虫种名之一，例如「蚜虫_01.jpg」。")
        return 1

    print(f"图集：{img_dir}")
    print(f"有效图片：{len(usable)} 张（跳过 {len(skipped)} 张）")
    print(f"置信度阈值：{settings.conf_threshold}")
    print("开始检测...\n")

    # 评测只关心 Top-1 结论，结果图没有保留价值：写到系统临时目录，
    # 且**每张图复用同一个路径覆盖写**，全程不做任何文件删除。
    # 原因：受限执行环境对批量删除有安全拦截（累计到阈值即中断进程），
    # 早期版本为每张图删一次临时文件，233 张图必然触发拦截、评测中途失败。
    tmp_dir = Path(tempfile.gettempdir()) / "pestguard_eval"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # 预热：首次推理包含模型加载（实测约 5 秒），不预热会把平均耗时拉高十几倍，
    # 与 benchmark 的 78.6ms 失去可比性。
    warm = tmp_dir / "_warmup.jpg"
    detector.predict_image(usable[0][0].read_bytes(), warm)
    print("（已预热，模型加载耗时不计入统计）\n")

    rows: list[dict] = []
    t_all = time.perf_counter()

    def blank_row(name: str, truth: str, group: str) -> dict:
        """字段集合必须与正常行完全一致，否则 DictWriter 会在写 CSV 时抛 ValueError。"""
        return {
            "file": name, "group": group, "truth": truth, "crop": "", "base_top1": "",
            "base_status": "error",
            "prior_top1": "", "prior_status": "error", "prior_applied": "",
            "conf": "", "n": 0, "ms": "", "detail": "",
        }

    for idx, (p, label) in enumerate(usable, 1):
        content = p.read_bytes()
        group = group_of(img_dir, p)
        # 固定文件名（按后缀区分）+ 覆盖写，不删除，理由见上方 tmp_dir 注释
        tmp = tmp_dir / f"_eval_tmp{p.suffix}"
        t0 = time.perf_counter()
        try:
            preds = detector.predict_image(content, tmp)
        except Exception as exc:  # noqa: BLE001
            rows.append(blank_row(p.name, label, group))
            print(f"  [{idx}/{len(usable)}] {p.name} -> 出错：{exc}")
            continue
        ms = (time.perf_counter() - t0) * 1000

        # 本图的作物上下文：优先按文件名推断（一张图一个作物），否则用统一 --crop
        crop_used = None
        if args.crop_from_name:
            for c in sorted(crop_keys, key=len, reverse=True):
                if c in p.stem:
                    crop_used = c
                    break
        elif args.crop:
            crop_used = args.crop

        def judge(plist: list[dict], truth: str) -> tuple[str, str]:
            """返回 (top1名称, 判定)。空列表即漏检。"""
            if not plist:
                return "", "漏检"
            top = max(plist, key=lambda x: x["confidence"])
            name = top.get("class_cn") or top.get("class")
            if name == truth:
                return name, "命中"
            if any((x.get("class_cn") or x.get("class")) == truth for x in plist):
                return name, "任意命中"
            return name, "误判"

        base_top1, base_status = judge(preds, label)
        conf = max((x["confidence"] for x in preds), default=0.0)

        # 寄主先验：只重排、不增删。数量守恒由 host_prior 单测保证。
        prior_top1, prior_status, prior_applied = base_top1, base_status, ""
        if preds and crop_used:
            rr = host_prior.rerank(preds, crop_used)
            prior_top1, prior_status = judge(rr.predictions, label)
            prior_applied = "是" if rr.applied else "否"

        rows.append(
            {
                "file": p.name,
                "group": group,
                "truth": label,
                "crop": crop_used or "",
                "base_top1": base_top1,
                "base_status": base_status,
                "prior_top1": prior_top1,
                "prior_status": prior_status,
                "prior_applied": prior_applied,
                "conf": round(conf, 4) if conf else "",
                "n": len(preds),
                "ms": round(ms, 1),
                "detail": " / ".join(
                    f'{x.get("class_cn") or x.get("class")}:{x["confidence"]:.2f}' for x in preds[:3]
                ),
            }
        )
        mark = "" if base_top1 == prior_top1 else f"  [先验: {prior_top1 or '无'}]"
        print(f"  [{idx}/{len(usable)}] {p.name}  真值={label}  ->  {base_top1 or '无检出'} ({base_status}){mark}")

    elapsed = time.perf_counter() - t_all

    n = len(rows)
    valid = [r for r in rows if r["base_status"] != "error"]
    n_err = n - len(valid)

    def hit_count(rs: list[dict], key: str) -> int:
        return sum(1 for r in rs if r[key] == "命中")

    n_hit = hit_count(valid, "base_status")
    n_any = sum(1 for r in valid if r["base_status"] in ("命中", "任意命中"))
    n_miss = sum(1 for r in valid if r["base_status"] == "漏检")
    n_wrong = sum(1 for r in valid if r["base_status"] == "误判")
    lat = [r["ms"] for r in valid if isinstance(r["ms"], (int, float))]
    avg_ms = sum(lat) / len(lat) if lat else 0
    base_rate = n_hit / len(valid) * 100 if valid else 0.0

    # ── 寄主先验 A/B ──
    ab_on = bool(args.crop or args.crop_from_name)
    p_hit = hit_count(valid, "prior_status") if ab_on else n_hit
    prior_rate = p_hit / len(valid) * 100 if valid else 0.0
    delta = prior_rate - base_rate
    # 被救回来的 / 被改坏的 —— 后者哪怕只有一条也说明 alpha 调过头了
    fixed = [r for r in valid if r["base_status"] != "命中" and r["prior_status"] == "命中"]
    broken = [r for r in valid if r["base_status"] == "命中" and r["prior_status"] != "命中"]
    applied_n = sum(1 for r in valid if r["prior_applied"] == "是")

    # 按数据来源分组：田間实拍 / 标本 / 公开图集 必须分开看，
    # 混在一起报一个总数，等于默认了「三者难度相同」，评委一问就露。
    by_group: dict[str, dict] = defaultdict(lambda: {"total": 0, "hit": 0})
    for r in valid:
        g = by_group[r["group"]]
        g["total"] += 1
        if r["base_status"] == "命中":
            g["hit"] += 1

    # 按虫种聚合（基线口径）
    by_species: dict[str, dict] = defaultdict(lambda: {"total": 0, "hit": 0, "miss": 0, "phit": 0})
    for r in valid:
        s = by_species[r["truth"]]
        s["total"] += 1
        if r["base_status"] == "命中":
            s["hit"] += 1
        if r["base_status"] == "漏检":
            s["miss"] += 1
        if ab_on and r["prior_status"] == "命中":
            s["phit"] += 1

    # 混淆对：真实 -> Top1（仅误判）
    confuse = Counter()
    for r in valid:
        if r["base_status"] == "误判" and r["base_top1"]:
            confuse[(r["truth"], r["base_top1"])] += 1

    out_md = Path(args.out)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_csv = out_md.with_suffix(".csv")

    L: list[str] = []
    # 章节序号用中文数字：原实现用 chr(64+n) 生成 ASCII 字母，会输出「C、D、E」，
    # 与开头的「一、二」混在一起，正式材料里很突兀。
    NUM_CN = "零一二三四五六七八九十"
    def cn_num(i: int) -> str:
        return NUM_CN[i] if 0 <= i < len(NUM_CN) else str(i)

    L.append("# PestGuard 端到端准确率实测报告\n")
    L.append(f"- 图集目录：`{img_dir}`")
    if len(by_group) > 1:
        L.append("- 数据来源构成：" + " · ".join(
            f"{g} {v['total']} 张（命中 {v['hit']}）"
            for g, v in sorted(by_group.items(), key=lambda x: -x[1]["total"])
        ))
    L.append(f"- 置信度阈值：{settings.conf_threshold}")
    L.append(f"- 有效样本：**{len(valid)}** 张（跳过 {len(skipped)} 张，出错 {n_err} 张）")
    if ab_on:
        L.append(f"- 作物上下文：{'按文件名推断' if args.crop_from_name else args.crop}")
    L.append(f"- 总耗时：{elapsed:.1f} s，单图平均 **{avg_ms:.1f} ms**\n")

    L.append("## 一、总体结果\n")
    L.append("| 指标 | 数值 |")
    L.append("| --- | --- |")
    L.append(f"| **Top-1 命中率** | **{n_hit}/{len(valid)} = {base_rate:.1f}%** |")
    L.append(f"| 任意命中率（Top-K 包含真值） | {n_any}/{len(valid)} = {n_any / len(valid) * 100:.1f}% |")
    L.append(f"| 误判数 | {n_wrong} |")
    L.append(f"| 漏检数（0 检出） | {n_miss} |")
    L.append(f"| 处理出错 | {n_err} |")
    L.append(f"| 单图平均耗时 | {avg_ms:.1f} ms |")
    L.append("")
    L.append(f"> 答辩时建议直接说：**「{len(valid)} 张里对了 {n_hit} 张」**。\n")

    if ab_on:
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        L.append("## 二、寄主先验对照（同一批图，两次判定）\n")
        L.append("| 口径 | Top-1 命中 | 命中率 |")
        L.append("| --- | --- | --- |")
        L.append(f"| 仅检测模型（基线） | {n_hit}/{len(valid)} | {base_rate:.1f}% |")
        L.append(f"| 检测 + 寄主先验 | {p_hit}/{len(valid)} | {prior_rate:.1f}% |")
        L.append(f"| **提升** | **{p_hit - n_hit:+d}** | **{delta:+.1f} 个百分点 {arrow}** |")
        L.append("")
        L.append(f"- 先验实际改变排序的样本：{applied_n} / {len(valid)} 张")
        L.append(f"- 被先验纠正（原错→对）：{len(fixed)} 张")
        L.append(f"- 被先验改坏（原对→错）：**{len(broken)} 张**")
        L.append("")

        if fixed:
            L.append("### 2.1 被纠正的样本（收益来源）\n")
            L.append("| 图片 | 真实虫种 | 基线判成 | 先验后 |")
            L.append("| --- | --- | --- | --- |")
            for r in fixed:
                L.append(f"| {r['file']} | {r['truth']} | {r['base_top1'] or '无检出'} | {r['prior_top1']} |")
            L.append("")
        else:
            L.append("### 2.1 被纠正的样本（收益来源）\n")
            L.append("本轮没有出现「基线判错、先验救回」的样本。")
            L.append("这不代表先验无效 —— 常见原因见本节末尾的说明。\n")

        if broken:
            L.append("### 2.2 被改坏的样本（代价）\n")
            L.append("| 图片 | 真实虫种 | 基线正确 | 先验后判成 |")
            L.append("| --- | --- | --- | --- |")
            for r in broken:
                L.append(f"| {r['file']} | {r['truth']} | ✓ | {r['prior_top1']} |")
            L.append("")
            L.append("> **这一节比上一节更重要。** 出现被改坏的样本说明 `host_prior.json` 里的")
            L.append("> `alpha_*` 加权过猛，或该作物的寄主标签本身有问题。")
            L.append("> 处理方式：调小 `alpha_strong` / `alpha_conflict`（`floor` 不要动，它是安全底线），")
            L.append("> 或核对对应虫种在知识库里的 `tags` 是否打错，然后重跑本脚本。")
            L.append("> **不要直接删掉这一节，也不要假装它不存在。**\n")
        else:
            L.append("### 2.2 被改坏的样本（代价）\n")
            L.append("本轮对照中，先验**没有**把任何原本判对的样本改错。")
            L.append("这是可以写进材料的结论 —— 它证明当前加权幅度是安全的。\n")

        if delta <= 0 and (fixed or broken):
            L.append("> 提示：提升不明显或为负。常见原因是本批图集里")
            L.append("> 广谱害虫（蚜虫/蓟马/红蜘蛛等）占比过高 —— ")
            L.append("> 这些虫种在**任何作物上都可能出现**，先验按设计不对其加权，")
            L.append("> 因此它们不会带来提升。想让先验发挥作用，图集需要包含更多")
            L.append("> 与具体作物绑定的虫种（水稻三虫、葡萄六虫、柑橘七虫、麦类四虫）。\n")

    sec = 3 if ab_on else 2
    L.append(f"## {cn_num(sec)}、分虫种命中率\n")
    if ab_on:
        L.append("| 虫种 | 样本数 | 基线命中 | 先验命中 | 命中率 | 漏检 |")
        L.append("| --- | --- | --- | --- | --- | --- |")
        for sp, v in sorted(by_species.items(), key=lambda x: (-x[1]["total"], x[0])):
            rate = v["hit"] / v["total"] * 100
            L.append(f"| {sp} | {v['total']} | {v['hit']} | {v['phit']} | {rate:.0f}% | {v['miss']} |")
    else:
        L.append("| 虫种 | 样本数 | Top-1 命中 | 命中率 | 漏检 |")
        L.append("| --- | --- | --- | --- | --- |")
        for sp, v in sorted(by_species.items(), key=lambda x: (-x[1]["total"], x[0])):
            rate = v["hit"] / v["total"] * 100
            L.append(f"| {sp} | {v['total']} | {v['hit']} | {rate:.0f}% | {v['miss']} |")
    L.append("")
    # 样本量不足的虫种单独点出来，防止用 1 张图就宣称「该虫种 100%」
    thin = [sp for sp, v in by_species.items() if v["total"] < 3]
    if thin:
        L.append(f"> ⚠ 以下虫种样本不足 3 张，其命中率不具备统计意义，材料中请勿单独引用：")
        L.append(f"> {'、'.join(sorted(thin))}\n")

    if confuse:
        sec += 1
        L.append(f"## {cn_num(sec)}、主要混淆对\n")
        L.append("| 真实虫种 | 被识别为 | 次数 |")
        L.append("| --- | --- | --- |")
        for (t, p), c in confuse.most_common(15):
            L.append(f"| {t} | {p} | {c} |")
        L.append("")
        L.append("> 这张表是答辩的**加分项**：主动承认形态相近虫种存在混淆，")
        L.append("> 比被评委问出来强得多。\n")

    if len(by_group) > 1:
        sec += 1
        L.append(f"## {cn_num(sec)}、数据来源构成\n")
        L.append("| 数据来源 | 样本数 | Top-1 命中 | 命中率 |")
        L.append("| --- | --- | --- | --- |")
        for g, v in sorted(by_group.items(), key=lambda x: -x[1]["total"]):
            rate = v["hit"] / v["total"] * 100
            L.append(f"| {g} | {v['total']} | {v['hit']} | {rate:.1f}% |")
        L.append("")
        L.append("> 不同来源必须分开统计：**田间实拍**最难（远、糊、逆光），")
        L.append("> **标本照**的取景条件与训练集最接近（通常偏容易），")
        L.append("> **公开图集**十有八九是别人挑出来的精选图。")
        L.append("> 三者混在一起报一个数，等于默认它们难度相同 —— 评委一问就露。")
        L.append("> 材料中务必写明各来源占比。\n")

    sec += 1
    L.append(f"## {cn_num(sec)}、逐图明细\n")
    if ab_on:
        L.append("| 图片 | 来源 | 作物 | 真实虫种 | 基线 Top-1 | 先验 Top-1 | 排序变化 | 置信度 | 判定 | 耗时 ms |")
        L.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for r in rows:
            L.append(
                f"| {r['file']} | {r['group']} | {r['crop'] or '—'} | {r['truth']} | {r['base_top1'] or '—'} "
                f"| {r['prior_top1'] or '—'} | {r['prior_applied'] or '—'} "
                f"| {r['conf'] or '—'} | {r['base_status']} | {r['ms'] or '—'} |"
            )
    else:
        L.append("| 图片 | 来源 | 真实虫种 | Top-1 预测 | 置信度 | 检出数 | 判定 | 耗时 ms |")
        L.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for r in rows:
            L.append(
                f"| {r['file']} | {r['group']} | {r['truth']} | {r['base_top1'] or '—'} | {r['conf'] or '—'} "
                f"| {r['n']} | {r['base_status']} | {r['ms'] or '—'} |"
            )
    L.append("")

    if skipped:
        sec += 1
        L.append(f"## {cn_num(sec)}、跳过的文件\n")
        L.append("| 文件 | 原因 |")
        L.append("| --- | --- |")
        for f, why in skipped:
            L.append(f"| {f} | {why} |")
        L.append("")

    out_md.write_text("\n".join(L), encoding="utf-8")

    with out_csv.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print()
    print("=" * 56)
    print(f"Top-1 命中率：{n_hit}/{len(valid)} = {base_rate:.1f}%")
    print(f"任意命中率 ：{n_any}/{len(valid)} = {n_any / len(valid) * 100:.1f}%")
    print(f"误判 {n_wrong} · 漏检 {n_miss} · 出错 {n_err}")
    print(f"单图平均 {avg_ms:.1f} ms")
    if ab_on:
        print("-" * 56)
        print(f"寄主先验({args.crop or '按文件名'})：{prior_rate:.1f}%  ({delta:+.1f} 个百分点)")
        print(f"  被纠正 {len(fixed)} 张 · 被改坏 {len(broken)} 张")
        if broken:
            print("  [注意] 存在被改坏的样本，说明加权过猛，请调小 alpha_* 后重跑")
    print("=" * 56)
    print(f"报告：{out_md}")
    print(f"明细：{out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
