# -*- coding: utf-8 -*-
"""从 junitxml 取权威测试数字（本机stdout 不可信，见任务说明）。"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

p = Path(r"D:\tmp_junit.xml")
root = ET.parse(p).getroot()
suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
tot = fail = err = skip = 0
for s in suites:
    tot += int(s.get("tests", 0))
    fail += int(s.get("failures", 0))
    err += int(s.get("errors", 0))
    skip += int(s.get("skipped", 0))
L = [
    f"junitxml = {p}",
    f"tests={tot} failures={fail} errors={err} skipped={skip} passed={tot-fail-err-skip}",
    "",
]
for s in suites:
    L.append(f"  {s.get('name')}: tests={s.get('tests')} failures={s.get('failures')} "
             f"errors={s.get('errors')} skipped={s.get('skipped')}")
    for tc in s.findall("testcase"):
        if tc.find("failure") is not None or tc.find("error") is not None:
            L.append(f"    [FAIL] {tc.get('name')}")
Path(r"D:\pestguard\backend\_junit_summary.txt").write_text("\n".join(L), encoding="utf-8")
print("ok")