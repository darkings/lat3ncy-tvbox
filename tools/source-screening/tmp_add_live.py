#!/usr/bin/env python3
"""将四川电信 IPTV 加入 live_candidates.json（保留原有 3 个候选）。"""

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
PATH = "/opt/ponyo-source-manager/config/live_candidates.json"

with open(PATH, encoding="utf-8") as f:
    data = json.load(f)

# 检查是否已存在
keys = {c.get("key") for c in data}
if "live_sctv" not in keys:
    data.append(
        {
            "key": "live_sctv",
            "name": "四川电信IPTV",
            "url": "https://cdn.jsdelivr.net/gh/darkings/lat3ncy-tvbox@main/subscription/sctv.m3u",
            "enabled": True,
        }
    )
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("已加入 live_sctv")
else:
    print("live_sctv 已存在")

print(json.dumps(data, ensure_ascii=False, indent=1))
