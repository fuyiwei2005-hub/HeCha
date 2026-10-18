# -*- coding: utf-8 -*-
"""生成测试集拍摄清单 + 寄主对照表。

为什么要自动生成而不是手写：
    46 类虫种、上百条寄主与科属关系，手写必然出错，而且改了知识库就对不上。
    这两个文档都从 data/host_prior.json 与 knowledge/*.json 现场推导，
    知识库一改，重跑即同步 —— 材料与系统永远一致。

产出：
    docs/参赛材料/测试集拍摄清单.md   （给组员执行）
    docs/寄主-害虫对照表.md            （给组员核实数据）

用法：
    .venv\\Scripts\\python.exe tools\\make_eval_plan.py
"""
from __future__ import annotations

import io
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROOT = Path(__file__).resolve().parents[1]
KB_DIR = ROOT / 'data' / 'knowledge'
PRIOR = ROOT / 'data' / 'host_prior.json'
OUT_DIR = ROOT.parent / 'docs' / '参赛材料'
OUT_TABLE = ROOT.parent / 'docs' / '寄主-害虫对照表.md'
OUT_PLAN = OUT_DIR / '测试集拍摄清单.md'

# 每类建议张数：近缘易混组要多拍，才能暴露真实问题
N_CONFUSABLE = 5
N_SENSITIVE = 4
N_BROAD = 3

# 拍照维度：同一种虫这几种情况都要覆盖，否则测出来的准确率是虚高的
SHOOT_ASPECTS = [
    '虫态覆盖：卵（块）/ 幼虫 / 若虫 / 成虫 至少各 1 张',
    '角度覆盖：叶片正面、背面各至少 1 张（多数害虫藏在叶背）',
    '尺度覆盖：远景（整叶/整株，虫体小）+ 近景（虫体占画面 1/4 以上）',
    '背景覆盖：单色背景 1 张 + 真实复杂背景（土面、枝干、杂草、花）若干',
    '难度覆盖：至少 1 张模糊 / 逆光 / 虫体被遮挡的“难样本”',
    '密度覆盖：单头 1 张 + 群集（多头聚集）1 张',
]


def load_prior() -> dict:
    if not PRIOR.is_file():
        print(f'[错误] 缺少 {PRIOR}，请先运行 tools/build_host_prior.py')
        raise SystemExit(2)
    return json.loads(PRIOR.read_text(encoding='utf-8'))


def load_families() -> dict[str, list[str]]:
    """从知识库 tags 里取「科」级分类，用于识别近缘易混组。"""
    fam: dict[str, list[str]] = defaultdict(list)
    for f in sorted(KB_DIR.glob('*.json')):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            continue
        if not isinstance(data, list):
            continue
        for it in data:
            if not isinstance(it, dict) or not str(it.get('id', '')).startswith('pest-'):
                continue
            name = it.get('name', '').strip()
            for t in it.get('tags', []):
                if t.endswith('科') and t not in ('科目',):
                    fam[t].append(name)
    return {k: v for k, v in fam.items() if len(v) >= 2}


def main() -> int:
    prior = load_prior()
    pests: dict = prior['pests']
    families = load_families()

    # 反向：虫种 -> 所属科（可能多个）
    pest_fams: dict[str, list[str]] = defaultdict(list)
    for fam, members in families.items():
        for m in members:
            pest_fams[m].append(fam)

    confusable = {p for p, fs in pest_fams.items() if fs}

    # 分组
    g_conf, g_sens, g_broad = [], [], []
    for cn, info in pests.items():
        if not info.get('class_en'):
            continue                      # 非模型类别的知识库条目
        gen = info.get('generality')
        if cn in confusable:
            g_conf.append(cn)
        elif gen in ('specific', 'family'):
            g_sens.append(cn)
        else:
            g_broad.append(cn)

    total = len(g_conf) * N_CONFUSABLE + len(g_sens) * N_SENSITIVE + len(g_broad) * N_BROAD

    # ── 对照表 ────────────────────────────────────────────────────────
    T: list[str] = []
    T.append('# PestGuard · 寄主-害虫对照表\n')
    T.append('> 本表由 `backend/tools/make_eval_plan.py` 从 `data/host_prior.json` 自动生成，')
    T.append('> 数据源为知识库 `data/knowledge/*.json` 的 `tags` 字段。')
    T.append('> **请逐行人工核实**，尤其是「广谱」部分 —— 广谱害虫在不同作物上的具体虫种往往不同')
    T.append('> （如蚜虫在小麦上是麦长管蚜、在棉花上是棉蚜），需要按作物细化。\n')

    T.append(f'- 模型可识别虫种：**{len(prior["meta"]["model_classes"])} 类**' if isinstance(prior['meta'].get('model_classes'), list)
             else f'- 模型可识别虫种：**{prior["meta"]["model_classes"]} 类**')
    T.append(f'- 有明确寄主标签：**{len(g_conf) + len(g_sens)} 类**')
    T.append(f'- 广谱/多寄主（不参与先验加权）：**{len(g_broad)} 类**')
    T.append(f'- 存在同科近缘虫种（易混淆）：**{len(confusable)} 类**\n')

    T.append('## 一、按寄主类目归类\n')
    # 按「寄主类目」而不是展开后的作物分组：果树类是 13 种作物的集合，
    # 若按作物展开，同样的 7 种虫会重复列 13 遍。
    by_tag: dict[str, list[str]] = defaultdict(list)
    for cn, info in pests.items():
        if not info.get('class_en'):
            continue
        for t in info.get('host_tags', []):
            by_tag[t].append(cn)

    tag_meta = prior.get('host_tag_meta', {})
    for tag, members in sorted(by_tag.items(), key=lambda x: -len(x[1])):
        meta = tag_meta.get(tag, {})
        label = meta.get('label', tag)
        region = meta.get('region', '')
        crop_list = '、'.join(meta.get('members', [])[:12]) or tag
        T.append(f'### {label}（{region}）\n')
        T.append(f'- 代表作物：{crop_list}')
        T.append(f'- 常见害虫（{len(members)}）：{"、".join(sorted(members))}\n')

    T.append('## 二、按虫种归类\n')
    T.append('| 虫种 | 英文类别名 | 寄主专一性 | 关联寄主 | 所属科 | 备注 |')
    T.append('| --- | --- | --- | --- | --- | --- |')
    GEN_CN = {'specific': '专性', 'family': '类级', 'broad': '广谱', 'unknown': '未标注'}
    for cn in sorted(pests, key=lambda k: (pests[k].get('generality', 'z'), k)):
        info = pests[cn]
        if not info.get('class_en'):
            continue
        hosts = '、'.join(info.get('host_labels', [])) or '—'
        fams = '、'.join(pest_fams.get(cn, [])) or '—'
        gen = GEN_CN.get(info.get('generality'), '—')
        note = ''
        if info.get('generality') in ('broad', 'unknown'):
            note = '任何作物都可能出现，**请补充主要危害作物**'
        if cn in confusable:
            note = (note + ' ' if note else '') + '近缘易混，需重点取样'
        T.append(f'| {cn} | {info["class_en"]} | {gen} | {hosts} | {fams} | {note.strip()} |')
    T.append('')

    T.append('## 三、需人工补充的条目\n')
    nom = prior['meta'].get('pests_without_host_tag', [])
    T.append(f'以下 {len(nom)} 类在知识库里**没有寄主标签**，本表无法给出寄主约束：\n')
    T.append('| 虫种 | 请补充：主要危害作物 | 是否有文献依据 |')
    T.append('| --- | --- | --- |')
    for cn in nom:
        T.append(f'| {cn} |  |  |')
    T.append('')
    T.append('> 补充方式：编辑 `backend/data/knowledge/pests_cereal.json` 或 `pests_fruit.json`，')
    T.append('> 在该条目的 `tags` 里加上作物名（如 `"小麦"`），然后重跑：')
    T.append('> `python tools/build_host_prior.py` → `python tools/make_eval_plan.py`\n')

    OUT_TABLE.parent.mkdir(parents=True, exist_ok=True)
    OUT_TABLE.write_text('\n'.join(T), encoding='utf-8')

    # ── 拍摄清单 ──────────────────────────────────────────────────────
    P: list[str] = []
    P.append('# PestGuard · 测试集拍摄清单\n')
    P.append('**目的**：给评委一个「在真实场景下能用」的证据。')
    P.append('训练集已丢失，本清单产出的图集是**唯一**能证明端到端准确率的东西。\n')
    P.append(f'- 建议总量：**约 {total} 张**（可按人力压缩到 60%，但要保证每组至少 3 张）')
    P.append('- 命名规则：**文件名里必须包含虫种中文名**，脚本靠它当真实标签')
    P.append('  - 正确：`稻纵卷叶螟_01.jpg`、`蚜虫_小麦田_模糊.jpg`')
    P.append('  - 错误：`IMG_20260924.jpg`（脚本认不出真值，会被跳过）')
    P.append('- 若同时要用寄主先验做对照，文件名里再带上作物名：`玉米螟_玉米_01.jpg`\n')
    P.append('---\n')

    P.append('## 拍照要求（每种虫都要覆盖）\n')
    for i, s in enumerate(SHOOT_ASPECTS, 1):
        P.append(f'{i}. {s}')
    P.append('')
    P.append('> 只拍「虫体占满画面、光线充足」的图，测出来的准确率没有意义 ——')
    P.append('> 真实农户拍的图就是这样：远、糊、逆光、虫还小。**难样本才是分数的来源。**\n')

    def section(title: str, items: list[str], n: int, why: str, check: str) -> None:
        if not items:
            return
        P.append(f'## {title}（{len(items)} 类 × 建议 {n} 张 = {len(items) * n} 张）\n')
        P.append(f'**为什么先拍这些**：{why}\n')
        P.append('| # | 虫种 | 寄主 | 所在科 | 寄主先验 | 建议张数 | 拍摄要点 |')
        P.append('| --- | --- | --- | --- | --- | --- | --- |')
        for i, cn in enumerate(sorted(items), 1):
            info = pests[cn]
            # 用 host_labels 而不是 hosts：后者是展开后的作物清单，
            # 截前三个会显示成「山楂、李、杏」，把「果树类」误读成三种具体作物
            hosts = '、'.join(info.get('host_labels', [])) or '广谱'
            fams = '、'.join(pest_fams.get(cn, [])) or '—'
            # 广谱虫在任何作物上都可能出现，先验按设计不动它们 ——
            # 不标明的话，组员会以为拍了这些就能证明先验有效（实测下来是 0 提升）
            gen = info.get('generality')
            prior_col = '不参与' if gen in ('broad', 'unknown') else f'参与（{GEN_CN.get(gen, "—")}）'
            P.append(f'| {i} | {cn} | {hosts} | {fams} | {prior_col} | {n} | {check} |')
        P.append('')

    section(
        'P0-A 近缘易混组', g_conf, N_CONFUSABLE,
        '这些虫种在同一科内，形态高度相似，是模型最容易翻车、也最能体现细粒度识别能力的地方。'
        '能把它们区分开，才有资格说“46 类细粒度识别”。',
        '同科近缘，需拍不同虫态以便区分',
    )
    section(
        'P0-B 寄主专性明确的虫种', g_sens, N_SENSITIVE,
        '这些虫种的寄主明确，是「寄主先验」功能唯一起作用的地方。'
        '想证明先验有效，必须优先拍它们；拍广谱害虫是测不出提升的。',
        '按寄主作物取景，文件名带上作物',
    )
    section(
        'P0-C 广谱/多寄主害虫', g_broad, N_BROAD,
        '用于检验模型的通用识别能力，也是混淆统计的主要来源。'
        '注意：这类虫的寄主先验按设计不加权，**它们的准确率不会因为加了先验而变化**。',
        '可在任意作物上拍摄',
    )

    P.append('## 拍照后的处理流程\n')
    P.append('1. 全部图片放进 `D:/pestguard/_实测图集/`')
    P.append('2. 运行基线实测：')
    P.append('   ```')
    P.append('   cd D:/pestguard/backend')
    P.append('   .\\.venv\\Scripts\\python.exe tools\\eval_top1.py')
    P.append('   ```')
    P.append('3. 若要验证寄主先验的提升，再加一次对照跑：')
    P.append('   ```')
    P.append('   .\\.venv\\Scripts\\python.exe tools\\eval_top1.py --crop-from-name --ab')
    P.append('   ```')
    P.append('   （文件名的作物名要能被识别，如 `玉米螟_玉米_01.jpg` 会自动带上「玉米」）')
    P.append('4. 报告输出到 `docs/参赛材料/准确率实测报告.md`，**直接引用其中的数字**\n')
    P.append('## 提交前自查\n')
    P.append('- [ ] 每类至少 3 张，近缘组至少 5 张')
    P.append('- [ ] 每类都包含至少 1 张「难样本」（模糊/逆光/遮挡）')
    P.append('- [ ] 文件名全部含虫种名，脚本无跳过项')
    P.append('- [ ] 已跑通 `eval_top1.py`，报告里「样本不足 3 张」的警告项已清除')
    P.append('- [ ] 若做了先验对照，「被改坏」列表已确认为 0，或已调小 alpha 后重跑\n')
    P.append('> 最后一条最关键：**先验把人家的正确答案改错，比不加先验更糟。**')

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PLAN.write_text('\n'.join(P), encoding='utf-8')

    print('=' * 60)
    print(f'模型类别         : {len([p for p in pests.values() if p.get("class_en")])}')
    print(f'近缘易混组 P0-A  : {len(g_conf)} 类 × {N_CONFUSABLE} = {len(g_conf) * N_CONFUSABLE} 张')
    print(f'寄主专性 P0-B    : {len(g_sens)} 类 × {N_SENSITIVE} = {len(g_sens) * N_SENSITIVE} 张')
    print(f'广谱害虫 P0-C    : {len(g_broad)} 类 × {N_BROAD} = {len(g_broad) * N_BROAD} 张')
    print(f'建议总量         : 约 {total} 张')
    print('=' * 60)
    print(f'已写入 {OUT_PLAN}')
    print(f'已写入 {OUT_TABLE}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
