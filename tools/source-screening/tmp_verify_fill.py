#!/usr/bin/env python3
"""验证 10 个目标源时段覆盖。"""

import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect("/opt/ponyo-source-manager/data/sources.db")

TARGETS = [
    "☀飞龙🔹秒播",
    "35-最大",
    "25-最大",
    "49-无忧",
    "1-艾旦",
    "21-爱胆",
    "lovedan.net┃GH",
    "360ZZ┃GH",
    "🎬飘零资源",
    "鸡坤资源",
]
ALL = ("morning", "noon", "evening", "night")
for name in TARGETS:
    row = con.execute(
        "SELECT n.fingerprint FROM norm_source n JOIN raw_source r ON n.raw_id=r.id WHERE r.name=? LIMIT 1",
        (name,),
    ).fetchone()
    if not row:
        continue
    slots = con.execute(
        "SELECT DISTINCT timeslot FROM conn_probe WHERE fingerprint=? AND ok=1",
        (row[0],),
    ).fetchall()
    st = sorted(s[0] for s in slots)
    missing = [t for t in ALL if t not in st]
    mark = "✅ 4时段" if not missing else f"缺{missing}"
    print(f"  {name:<16} {mark}")
con.close()
