#!/usr/bin/env python3
"""查看 4 新源的 media 失败详情。"""

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

m = json.load(open("/opt/ponyo-source-manager/reports/maccms-media-report.json"))
res = m.get("results", [])
hosts = ["yhzy.cc", "suboziyuan.net", "zy.xiaomaomi.cc", "maoyanapi"]
for r in res:
    ep = str(r.get("endpoint") or r.get("input_url") or "")
    if any(h in ep for h in hosts):
        print("=" * 80)
        print("endpoint:", ep)
        print(json.dumps(r, ensure_ascii=False, indent=1)[:1500])
