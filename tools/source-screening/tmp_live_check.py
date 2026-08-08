#!/usr/bin/env python3
"""排查：live sctv=0 原因 + collector ssrf 根因。"""

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

print("== 四川电信 live 条目详情 ==")
lr = json.load(open("/opt/ponyo-source-manager/reports/live-report.json"))
for c in lr.get("candidates", []):
    if "四川电信" in c.get("name", "") or "sctv" in str(c.get("key", "")):
        print(json.dumps(c, ensure_ascii=False, indent=1)[:2000])
        break
else:
    # 打印前 3 个条目的关键字段
    for c in lr.get("candidates", [])[:3]:
        print(
            json.dumps(
                {k: c[k] for k in ("key", "name", "url", "validity_rate", "hard_pass")},
                ensure_ascii=False,
            )
        )
