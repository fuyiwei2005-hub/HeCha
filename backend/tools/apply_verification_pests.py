# -*- coding: utf-8 -*-
"""按第二轮查证结果回填 C 组虫种发生期（pests_cereal / pests_fruit）"""
import json, pathlib, shutil, datetime

B = pathlib.Path(r'D:\pestguard\backend\data\knowledge')
FILES = ['pests_cereal.json', 'pests_fruit.json']

stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M')
for f in FILES:
    p = B / f
    shutil.copy2(p, p.with_suffix(f'.bak_{stamp}.json'))
print('已备份两份文件')

# file -> [(id, old, new, note)]
JOBS = {
 'pests_cereal.json': [
  ('pest-011',
   '成虫白天活动，具假死性，对糖醋液、发酵果味有强趋性，6–8 月为成虫盛发期',
   '成虫白天活动，具假死性，对糖醋液、发酵果味有强趋性；一般自 5 月上旬起陆续出现，6–8 月为成虫盛发期',
   '白星花金龟补 5 月上旬始见'),
  ('pest-013',
   '发生规律：一年发生多代，以成螨或卵在麦田及田边杂草上越冬',
   '发生规律：一年发生 2–3 代，以成螨或卵在麦田及田边杂草上越冬',
   '麦圆叶爪螨代数具体化'),
  ('pest-020',
   '发生规律：一年一代，幼虫在土中越冬并取食蝗卵',
   '发生规律：北方一年一代，幼虫在土中越冬并取食蝗卵',
   '豆芫菁限定北方口径'),
 ],
 'pests_fruit.json': [
  ('pest-024',
   '发生规律：一年发生多代，以成螨在芽鳞片下',
   '发生规律：一年发生多代（各地资料对代数记载不一），以成螨在芽鳞片下',
   '葡萄瘿螨注明记载差异'),
  ('pest-027',
   '发生规律：一年发生多代，以卵或若虫在树皮裂缝',
   '发生规律：华北地区一年约 3 代（南方部分地区代数更多），以卵或若虫在树皮裂缝',
   '康氏粉蚧代数具体化'),
  ('pest-034',
   '发生规律：一年发生多代，繁殖极快，以成螨在腋芽',
   '发生规律：南方一年可发生 18–24 代，繁殖极快，以成螨在腋芽',
   '柑橘锈螨代数修正'),
 ],
}

# 出处更新（stb.mae.edu.cn 存疑，故 pest-027 不写入该域名，仅标注已核对）
SOURCES = {
 'pest-011': '整理自《中国果树害虫志》金龟类部分；发生期经新疆农业大学公开资料核对（ifarm.xjau.edu.cn）',
 'pest-013': '整理自全国农业技术推广服务中心麦类病虫害防治技术方案；发生期经山西夏县农业农村局公开资料核对（sxxiaxian.gov.cn）',
 'pest-020': '整理自《农作物病虫害防治手册》豆类害虫部分；发生期经兰州市农业农村局公开资料核对（nync.lanzhou.gov.cn）',
 'pest-024': '整理自《中国果树害虫志》葡萄害虫部分；发生期经甘肃省农业农村厅公开资料核对（nync.gansu.gov.cn）',
 'pest-027': '整理自《中国果树害虫志》蚧类部分；发生代数经第二轮查证核对（华北以 3 代为主）',
 'pest-034': '整理自《中国果树害虫志》柑橘害虫部分；代数经衢州市农业农村局公开资料核对（nyncj.qz.gov.cn）',
}

tot_ok = tot_miss = 0
for fname, jobs in JOBS.items():
    p = B / fname
    kb = json.loads(p.read_text(encoding='utf-8'))
    idx = {x['id']: x for x in kb}
    print(f'\n--- {fname} ---')
    for cid, old, new, note in jobs:
        it = idx.get(cid)
        if it is None:
            print(f'  [缺条目] {cid}'); tot_miss += 1; continue
        if old in it['content']:
            it['content'] = it['content'].replace(old, new)
            print(f'  [OK] {cid} · {note}'); tot_ok += 1
        else:
            print(f'  [未命中] {cid} · {note}'); tot_miss += 1
    for cid, s in SOURCES.items():
        if cid in idx:
            idx[cid]['source'] = s
            print(f'  [source] {cid} 已更新')
    p.write_text(json.dumps(kb, ensure_ascii=False, indent=2), encoding='utf-8')

print(f'\n完成：成功 {tot_ok} 处，异常 {tot_miss} 处')
