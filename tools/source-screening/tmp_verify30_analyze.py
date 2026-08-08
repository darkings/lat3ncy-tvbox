#!/usr/bin/env python3
"""分析 verify30 探测结果。"""

import json
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

d = json.load(open("/tmp/verify30-report.json"))
print("run_id:", d.get("run_id"))
print("generated_at:", d.get("generated_at"))
print("queued:", d.get("queued"), "budget:", d.get("endpoint_budget"))
res = d.get("results", [])
print("结果数:", len(res))

c = Counter(r.get("failure_stage") or "passed" for r in res)
print("分布:", dict(c))

print("\n== 通过 ==")
for r in res:
    if r.get("passed"):
        n = sum(p.get("playable_url_count", 0) for p in r.get("probes", []))
        print(f"  ✅ {r['endpoint'][:60]:<62} playable合计={n}")

print("\n== 失败明细 ==")
for r in res:
    if not r.get("passed"):
        print(f"  ❌ {r['endpoint'][:60]:<62} {r.get('failure_stage')}")
