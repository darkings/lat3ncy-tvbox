#!/usr/bin/env python3
"""分析 type4 源形态。"""

import sqlite3
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect("/opt/ponyo-source-manager/data/sources.db")

n4 = con.execute("SELECT COUNT(*) FROM raw_source WHERE type=4").fetchone()[0]
print(f"type4 总数: {n4}")

rows = con.execute("SELECT name, api, ext FROM raw_source WHERE type=4").fetchall()
forms = Counter()
for name, api, ext in rows:
    api = api or ""
    if "127.0.0.1" in api:
        forms["本地服务(127.0.0.1)"] += 1
    elif api.startswith("csp") or "csp_" in api:
        forms["csp驱动"] += 1
    elif ".js" in api or "drpy" in api.lower():
        forms["drpy js"] += 1
    elif api.startswith("http"):
        forms["远程http"] += 1
    elif not api:
        forms["无api"] += 1
    else:
        forms["其他"] += 1
print("形态分布:", dict(forms))

print("\n== 样本(前 18) ==")
for name, api, ext in rows[:18]:
    print(f"  {str(name)[:22]:<24} api={str(api)[:68]}")

print("\n== type4 远程 http（非本地、非js）==")
r2 = con.execute(
    "SELECT name, api FROM raw_source WHERE type=4 AND api LIKE 'http%' "
    "AND api NOT LIKE '%127.0.0.1%' AND api NOT LIKE '%.js%' LIMIT 12"
).fetchall()
for name, api in r2:
    print(f"  {str(name)[:22]:<24} {str(api)[:75]}")

con.close()
