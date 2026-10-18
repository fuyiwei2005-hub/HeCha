# -*- coding: utf-8 -*-
"""从已核过的知识库 tags 自动生成寄主先验表 data/host_prior.json。

设计原则（重要）：
1. **数据来源可溯源** —— 全部字段来自 backend/data/knowledge/*.json 的 tags，
   不写死任何虫种-作物对应关系，知识库改了重跑本脚本即生效。
2. **只做软加权，永不归零** —— 见 scoring.floor。植物/作物识别一旦出错，
   最坏情况只是排名下降，绝不能让本来检得出的害虫消失（植保场景漏报 >> 误报）。
3. **默认保守** —— alpha 系数为启发式初值，**未经评测校准**。
   跑通 tools/eval_top1.py 拿到 baseline 后必须回来调参，别拿默认值当结论。

用法：
    .venv\\Scripts\\python.exe tools\\build_host_prior.py [--check]
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROOT = Path(__file__).resolve().parents[1]
KB_DIR = ROOT / 'data' / 'knowledge'
OUT = ROOT / 'data' / 'host_prior.json'
NAMES_PY = ROOT / 'app' / 'services' / 'pest_names.py'

# ── 寄主 tag -> 作物语义 ────────────────────────────────────────────────
# 每个 tag 显式给出 strong / related：
#   strong  —— 虫种在该作物上属典型、专性或优势危害，给高权重
#   related —— 同科/同类作物，可能发生但非典型，给低权重
# 不写死虫种名单，名单由知识库 tags 反查生成，这里只描述"作物 ↔ tag"的语义。
HOST_TAGS: dict[str, dict] = {
    '水稻': {
        'label': '水稻', 'region': '南方及东北主栽',
        'strong': ['水稻'], 'related': [],
    },
    '玉米': {
        'label': '玉米', 'region': '全国，华北主栽',
        'strong': ['玉米'], 'related': [],
    },
    '麦类': {
        'label': '麦类', 'region': '华北主栽',
        'strong': ['小麦', '大麦'], 'related': ['燕麦', '青稞'],
    },
    '葡萄': {
        'label': '葡萄', 'region': '全国，华北优势产区',
        'strong': ['葡萄'], 'related': [],
    },
    '柑橘': {
        'label': '柑橘类', 'region': '南方主栽（华北温室偶见）',
        'strong': ['柑橘', '橙', '柚', '柠檬'], 'related': [],
    },
    '藜科': {
        'label': '藜科作物', 'region': '华北（甜菜）主栽',
        'strong': ['甜菜'], 'related': ['菠菜'],
    },
    '十字花科': {
        'label': '十字花科蔬菜', 'region': '全国',
        'strong': ['白菜', '甘蓝', '油菜', '萝卜', '花椰菜', '芥菜'], 'related': [],
    },
    '豆类': {
        'label': '豆类作物', 'region': '华北主栽',
        'strong': ['大豆', '花生', '绿豆', '豇豆', '菜豆', '豌豆'], 'related': ['苜蓿'],
    },
    # 果树是泛类：果树害虫普遍跨寄主（苹果/梨/桃都能危害），一律弱权重
    '果树': {
        'label': '果树（泛）', 'region': '全国',
        'strong': [], 'related': [
            '苹果', '梨', '桃', '李', '杏', '柿', '枣', '山楂',
            '石榴', '猕猴桃', '樱桃', '核桃', '板栗'],
    },
}

# 下拉框里额外提供的华北常见作物（知识库无专性虫也能走 related 层）
EXTRA_CROPS = ['棉花', '马铃薯', '向日葵', '番茄', '黄瓜', '辣椒', '草莓']

# ── 作物显示名 ──────────────────────────────────────────────────────────
# 知识库 tags 里的作物名是分类学简称，单字的那批（李/杏/柿/桃/橙/柚…）
# 直接显示在下拉框里会被读成"名字不全" —— 用户看到的是「李」而不是「李子」。
# 所以这里给显示名做一层映射：**只改展示，不动 key**。
#
# 为什么必须保留 key 不变：
#   key 是虫种—作物映射的主键，也是 detections.crop 落库的值。
#   改它等于让历史记录失效，还会连带破坏 pest 侧的 strong/related 名单。
CROP_LABEL_ALIAS: dict[str, str] = {
    '李': '李子',
    '杏': '杏子',
    '柿': '柿子',
    '桃': '桃子',
    '橙': '橙子',
    '柚': '柚子',
    '枣': '枣树',
    '梨': '梨树',
}

# ── 输入别名（口语/俗名 -> key）──────────────────────────────────────────
# 显示名改了之后，用户手输或别处传来的会是「李子」「西红柿」这类叫法。
# 不认这些别名的话，先验会静默失效（判为未知作物）—— 属于隐性功能丢失，
# 所以一并收进来吃掉。'key 本身'永远有效，这里只补额外写法。
CROP_INPUT_ALIAS: dict[str, str] = {
    '李子': '李', '李树': '李',
    '杏子': '杏', '杏树': '杏',
    '柿子': '柿', '柿子树': '柿', '柿树': '柿',
    '桃子': '桃', '桃树': '桃',
    '橙子': '橙', '桔子': '柑橘', '橘子': '柑橘',
    '柚子': '柚', '柚子树': '柚',
    '梨子': '梨',
    '枣子': '枣', '大枣': '枣', '红枣': '枣',
    '西红柿': '番茄', '圣女果': '番茄',
    '土豆': '马铃薯', '洋芋': '马铃薯',
    '包菜': '甘蓝', '卷心菜': '甘蓝', '圆白菜': '甘蓝',
    '黄豆': '大豆',
    '苞谷': '玉米', '苞米': '玉米',
    '稻谷': '水稻', '稻子': '水稻',
    '麦子': '小麦',
    '青椒': '辣椒', '尖椒': '辣椒',
}

# 算作「广谱」的标记
BROAD_TAG = '多寄主'

SCORING = {
    'alpha_strong': 0.35,     # 专性寄主命中：稻纵卷叶螟 on 水稻
    'alpha_related': 0.18,    # 同类作物命中：桃蛀螟 on 苹果（果树泛类）
    'alpha_conflict': -0.25,  # 寄主明显冲突：柑橘锈螨 on 小麦
    'floor': 0.5,             # 权重下限因子 —— 硬底线，永不让任何候选归零
    'note': (
        'new_score = old_score * (1 + alpha)。alpha 为启发式初值，'
        '必须用 tools/eval_top1.py 的评测结果校准后才能写进设计文档。'
        'floor 保证最坏情况下某候选权重不低于原值的一半，'
        '宁可不提升也不允许漏检 —— 植保场景漏报代价远高于误报。'
    ),
}


def load_class_cn() -> dict[str, str]:
    """从 pest_names.py 读取 CLASS_CN（避免依赖 ultralytics）。"""
    ns: dict = {}
    exec(compile(NAMES_PY.read_text(encoding='utf-8'), 'pest_names.py', 'exec'), ns)
    return ns['CLASS_CN']


def load_pests() -> list[dict]:
    """读取知识库中的害虫条目（id 以 pest- 开头）。"""
    out: list[dict] = []
    for f in sorted(KB_DIR.glob('*.json')):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
        except json.JSONDecodeError as e:
            print(f'[警告] {f.name} 解析失败：{e}')
            continue
        if not isinstance(data, list):
            continue
        for it in data:
            if isinstance(it, dict) and str(it.get('id', '')).startswith('pest-'):
                out.append(it)
    return out


def normalize_tag(t: str) -> str:
    """兼容知识库里可能出现的异体字 / 错别字。"""
    return t.replace('黎科', '藜科').strip()


def build() -> dict:
    class_cn = load_class_cn()
    cn2en = {v: k for k, v in class_cn.items()}
    pests_kb = load_pests()

    pest_out: dict[str, dict] = {}
    crop_strong: dict[str, list[str]] = defaultdict(list)
    crop_related: dict[str, list[str]] = defaultdict(list)
    crop_tag: dict[str, str] = {}      # 具体作物 -> 所属 tag key
    unhosted: list[str] = []

    for tag, meta in HOST_TAGS.items():
        for m in meta['strong']:
            crop_tag.setdefault(m, tag)
        for m in meta['related']:
            crop_tag.setdefault(m, tag)

    for it in pests_kb:
        cn = it.get('name', '').strip()
        if not cn:
            continue
        tags = [normalize_tag(t) for t in it.get('tags', [])]
        host_tags = [t for t in tags if t in HOST_TAGS]
        is_broad = BROAD_TAG in tags

        if host_tags:
            # 所有寄主 tag 都只指向单一作物 => 专性；否则归为类级
            single = all(len(HOST_TAGS[t]['strong']) <= 1 for t in host_tags)
            generality = 'specific' if single else 'family'
        elif is_broad:
            generality = 'broad'
        else:
            generality = 'unknown'

        members: list[str] = []
        for t in host_tags:
            members.extend(HOST_TAGS[t]['strong'])
            members.extend(HOST_TAGS[t]['related'])

        pest_out[cn] = {
            'class_en': cn2en.get(cn, ''),
            'kb_id': it.get('id', ''),
            'generality': generality,
            'host_tags': host_tags,
            # 人类可读的寄主标签（如「果树（泛）」「麦类」）。
            # 展示时必须用这个，不能用 hosts —— hosts 是展开后的作物列表，
            # 截前几个展示会变成「山楂、李、杏」，把「果树类」误读成具体三种作物。
            'host_labels': [HOST_TAGS[t]['label'] for t in host_tags],
            'hosts': sorted(set(members)),
            'broad': is_broad,
        }

        if not host_tags:
            unhosted.append(cn)

        # 反查：作物 -> 害虫（同一作物只能落一层，strong 优先）
        for t in host_tags:
            for m in HOST_TAGS[t]['strong']:
                crop_strong[m].append(cn)
            for m in HOST_TAGS[t]['related']:
                if cn not in crop_strong[m]:
                    crop_related[m].append(cn)

    crops = []
    seen_strong_pests = set()
    all_crops = sorted(set(list(crop_tag.keys()) + EXTRA_CROPS))
    for c in all_crops:
        tag = crop_tag.get(c)
        if tag:
            meta = HOST_TAGS[tag]
            region = f'{meta["label"]}·{meta["region"]}' if c not in meta['strong'] else meta['region']
        else:
            region = '常见作物'
        strong = sorted(set(crop_strong.get(c, [])))
        related = sorted(set(p for p in crop_related.get(c, []) if p not in strong))
        n = len(strong) + len(related)
        crops.append({
            'key': c,
            # 显示名独立于 key：单字作物名（李/柿…）在下拉框里会被读成「名字不全」
            'label': CROP_LABEL_ALIAS.get(c, c),
            'aliases': sorted(k for k, v in CROP_INPUT_ALIAS.items() if v == c),
            'region': region,
            # 有先验的作物能改排序；没先验的仍会作为上下文喂给大模型改善建议措辞，
            # 不该因为「起不到排序作用」就把用户常种的作物从下拉框里删掉。
            'has_prior': n > 0,
            'strong': strong,
            'related': related,
        })

    # 模型 46 类里，知识库没覆盖到的（应该为空，非空说明知识库漏了）
    missing_model = [cn for cn in class_cn.values() if cn not in pest_out]
    # 知识库有、但不属于模型 46 类的害虫（不影响推理，仅供对照表展示）
    extra_kb = [cn for cn in pest_out if cn not in class_cn.values()]

    return {
        'meta': {
            'version': '1.0',
            'generated_by': 'backend/tools/build_host_prior.py',
            'source': 'backend/data/knowledge/*.json → tags 字段',
            'model_classes': len(class_cn),
            'covered': len([p for p in pest_out.values() if p['class_en']]),
            'missing_model_classes': missing_model,
            'non_model_kb_pests': extra_kb,
            'pests_without_host_tag': sorted(unhosted),
        },
        'scoring': SCORING,
        'crops': crops,
        'pests': pest_out,
        # 寄主类目元数据（tag -> 展示名/产区/包含作物）。
        # 展示层要按「寄主类目」分组，不能按展开后的作物分组 ——
        # 否则「果树」会被拆成 13 种作物，每种都重复列一遍同样的虫种，表长得没法看。
        'host_tag_meta': {
            t: {'label': m['label'], 'region': m['region'], 'members': m['strong'] + m['related']}
            for t, m in HOST_TAGS.items()
        },
    }


def report(d: dict) -> None:
    m = d['meta']
    print('=' * 62)
    print(f"模型类别        : {m['model_classes']}")
    print(f"先验表覆盖      : {m['covered']} / {m['model_classes']}")
    if m['missing_model_classes']:
        print(f"[!!] 未覆盖模型类 : {m['missing_model_classes']}")
    if m['non_model_kb_pests']:
        print(f"知识库非模型虫种 : {len(m['non_model_kb_pests'])} 条（不参与推理）")
    gen = defaultdict(int)
    for p in d['pests'].values():
        if p['class_en']:
            gen[p['generality']] += 1
    print(f"寄主专一性分布  : {dict(gen)}")
    print(f"作物条目        : {len(d['crops'])}")
    print(f"无寄主tag的害虫 : {len(m['pests_without_host_tag'])}")
    print('=' * 62)
    print('\n各作物可命中的候选虫种数：')
    for c in d['crops']:
        n = len(c['strong']) + len(c['related'])
        if n:
            print(f"  {c['key']:8s} strong={len(c['strong']):2d} related={len(c['related']):2d}  total={n:2d}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='只校验不写盘')
    args = ap.parse_args()

    d = build()
    report(d)

    m = d['meta']
    ok = True
    if m['missing_model_classes']:
        print(f"\n[错误] 有 {len(m['missing_model_classes'])} 个模型类别没有先验条目：{m['missing_model_classes']}")
        ok = False
    if m['covered'] != m['model_classes']:
        print(f"[警告] 覆盖率 {m['covered']}/{m['model_classes']}")
    if m['pests_without_host_tag']:
        print(f"[提示] 未带寄主 tag 的害虫 {len(m['pests_without_host_tag'])} 条："
              f"{m['pests_without_host_tag']}")

    if args.check:
        print('\n--check 模式，未写盘。')
        return 0 if ok else 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n已写入 {OUT}  ({OUT.stat().st_size / 1024:.1f} KB)')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
