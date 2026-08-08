#!/usr/bin/env python3
"""评估 type4 DS 源的可路由性与内容价值。"""

import sqlite3
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "/opt/ponyo-source-manager/src")

from ponyo_source_manager.probes.drpy_runner import classify_drpy_route

con = sqlite3.connect("/opt/ponyo-source-manager/data/sources.db")
rows = con.execute(
    "SELECT id, name, api, ext FROM raw_source WHERE type=4 AND api LIKE '%127.0.0.1%'"
).fetchall()
print(f"DS 源: {len(rows)}")

routes = Counter()
samples = []
for rid, name, api, ext in rows:
    try:
        r = classify_drpy_route({"id": rid, "name": name, "api": api, "ext": ext})
        routes[r["route"]] += 1
        samples.append((name, r["route"], r.get("content_lane")))
    except Exception as e:
        routes[f"ERR:{type(e).__name__}"] += 1

print("路由分布:", dict(routes))
print("\n== 高价值样本路由 ==")
KEY = [
    "短剧",
    "央视",
    "直播",
    "樱花",
    "人人",
    "剧海",
    "星辰",
    "番茄",
    "小说",
    "Emby",
    "音乐",
    "听书",
    "少儿",
]
for name, route, lane in samples:
    if any(k in str(name) for k in KEY):
        print(f"  {str(name)[:24]:<26} {route:<28} lane={lane}")

# drpy_run 历史：DS 源是否被测试过
print("\n== drpy_run 最近运行 ==")
try:
    r2 = con.execute(
        "SELECT route, COUNT(*), MAX(run_at) FROM drpy_run GROUP BY route ORDER BY MAX(run_at) DESC LIMIT 12"
    ).fetchall()
    for r in r2:
        print("  ", r)
except Exception as e:
    print("  drpy_run 查询失败:", e)
con.close()
