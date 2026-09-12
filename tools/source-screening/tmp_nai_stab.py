#!/usr/bin/env python3
"""奶子稳定性明细 + promote 条件。"""

import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect("/opt/ponyo-source-manager/data/sources.db")

fp = "c2f638574ccc361c14ab5d7d295dca5f40bc857ae7000f18c91925003ea9207f"
rows = con.execute(
    "SELECT timeslot, probed_at, target_url, ok FROM conn_probe "
    "WHERE fingerprint=? AND probed_at >= datetime('now', '-7 days') ORDER BY probed_at",
    (fp,),
).fetchall()
print("== 奶子 conn_probe 7 天明细 ==")
for r in rows:
    print(f"  {r[0]:<8} {r[1][:16]} ok={r[3]} {r[2][:55]}")

print("\n== promote 条件 ==")
sys.path.insert(0, "/opt/ponyo-source-manager/src")
from ponyo_source_manager.scoring.promote_demote import evaluate_promotion

try:
    r = evaluate_promotion(con, fp)
    print("奶子:", {k: r[k] for k in r if k != "errors"})
except Exception as e:
    print("ERR", e)
con.close()
