#!/usr/bin/env python3
"""查奶子指纹有效性和 fail 详情。"""

import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect("/opt/ponyo-source-manager/data/sources.db")

# 奶子指纹是否在库
fp = "c2f638574ccc360c14ab5d7d295dca5f40bc857ae7000f18c91925003ea9207f"
row = con.execute(
    "SELECT fingerprint, category FROM norm_source WHERE fingerprint=?", (fp,)
).fetchone()
print("奶子指纹在库:", row)
if not row:
    # 找奶子资源的真实指纹
    rows = con.execute(
        "SELECT n.fingerprint, r.name, r.api FROM norm_source n JOIN raw_source r ON n.raw_id=r.id WHERE r.name LIKE '%奶子%'"
    ).fetchall()
    print("奶子源:", rows)

# night 补测 fail 的 URL
rows2 = con.execute(
    "SELECT target_url, ok, err FROM conn_probe WHERE timeslot='night' AND probed_at >= '2026-08-09T19:00:00+00:00' ORDER BY id DESC LIMIT 12"
).fetchall()
print("\nnight 补测记录:")
for r in rows2:
    print(f"  ok={r[1]} {r[0][:60]} err={str(r[2])[:60]}")
con.close()
