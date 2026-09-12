#!/usr/bin/env python3
"""检查 20:00 轮 collector 报告。"""

import json
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

d = json.load(open("/opt/ponyo-source-manager/reports/maccms-discovery-report.json"))
print("generated_at:", d.get("generated_at"))
print("queued:", d.get("queued"), "budget:", d.get("endpoint_budget"))
res = d.get("results", [])
c = Counter(r.get("failure_stage") or "passed" for r in res)
print("分布:", dict(c), "| 总数:", len(res))

# 新源命中
NEW = [
    "wsyzy",
    "tyyszyapi",
    "dbzy5",
    "360zyzz",
    "suonizy",
    "souavzy",
    "xiaojizy",
    "heiliaozy",
    "xingba",
    "gh-",
    "mdzyapi",
    "ffm3u8",
    "snm3u8",
    "gsm3u8",
    "jinyingyun",
]
print("\n== 新源/变体命中 ==")
for r in res:
    ep = r.get("endpoint", "")
    if any(h in ep for h in NEW):
        print(
            f"  {ep[:68]:<71} passed={r.get('passed')} stage={r.get('failure_stage')}"
        )

print("\n== 通过 ==")
for r in res:
    if r.get("passed"):
        print(f"  ✅ {r['endpoint'][:68]}")
