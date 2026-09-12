#!/usr/bin/env python3
"""查高分源指纹，供定向 night 补测。"""

import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect("/opt/ponyo-source-manager/data/sources.db")

for kw in ["奶子", "爱坤", "360", "如意", "飘零"]:
    rows = con.execute(
        "SELECT n.fingerprint, r.name, r.api FROM norm_source n "
        "JOIN raw_source r ON n.raw_id=r.id WHERE r.name LIKE ? LIMIT 3",
        (f"%{kw}%",),
    ).fetchall()
    for fp, name, api in rows:
        slots = con.execute(
            "SELECT DISTINCT timeslot FROM conn_probe WHERE fingerprint=? AND ok=1 ORDER BY timeslot",
            (fp,),
        ).fetchall()
        print(f"{fp[:12]}  {name[:18]:<20} {[s[0] for s in slots]}  {api[:50]}")
con.close()
