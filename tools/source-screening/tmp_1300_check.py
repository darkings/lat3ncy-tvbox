#!/usr/bin/env python3
"""检查 13:00 轮 collector 报告（新排序验证）。"""

import json
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

d = json.load(open("/opt/ponyo-source-manager/reports/maccms-discovery-report.json"))
print("generated_at:", d.get("generated_at"))
print("queued:", d.get("queued"), "budget:", d.get("endpoint_budget"))
res = d.get("results", [])
print("结果数:", len(res))
c = Counter(r.get("failure_stage") or "passed" for r in res)
print("分布:", dict(c))

# 今天导入的新源（GH/变体/XMLjson/suonizy）
NEW_HOSTS = [
    "wsyzy",
    "tyyszyapi",
    "dbzy5",
    "360zyzz",
    "jyzyapi.com/provide/vod/from/jinyingyun",
    "suonizy",
    "ffm3u8",
    "snm3u8",
    "gsm3u8",
    "dyttm3u8",
    "xiaomaomi",
    "mdzyapi",
    "at/json",
    "lbapi",
]
print("\n== 新源命中 ==")
for r in res:
    ep = r.get("endpoint", "")
    if any(h in ep for h in NEW_HOSTS):
        print(
            f"  {ep[:70]:<73} passed={r.get('passed')} stage={r.get('failure_stage')}"
        )

print("\n== 通过的全部 ==")
for r in res:
    if r.get("passed"):
        print(f"  ✅ {r['endpoint'][:70]}")
