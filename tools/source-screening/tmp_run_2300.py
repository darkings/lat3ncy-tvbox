#!/usr/bin/env python3
"""分析 23:00 轮 + 当前 allow 状态。"""

import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

d = json.load(
    open("/opt/ponyo-source-manager/reports/pipeline-run-20260808230001-fb1389.json")
)
print("run:", d["run_id"], "timeslot:", d["timeslot"])
print("started:", d["started_at"], "finished:", d["finished_at"])
print("summary:", d["summary"])
print()
for s in d["stages"]:
    dur = (s.get("duration_ms") or 0) // 1000
    err = str(s.get("error") or "")[:100]
    print(f"{s['name']:<28} {s['status']:<7} {dur:>6}s  {err}")

print("\n== 当前 allow ==")
con = sqlite3.connect("/opt/ponyo-source-manager/data/sources.db")
rows = con.execute(
    "SELECT l.updated_at, r.name, r.api FROM list_state l "
    "JOIN norm_source n ON l.fingerprint=n.fingerprint "
    "JOIN raw_source r ON n.raw_id=r.id WHERE l.state='allow' ORDER BY l.updated_at"
).fetchall()
print(f"allow 总数: {len(rows)}")
for r in rows:
    print(f"  {r[0][:16]}  {r[1][:22]:<24} {r[2][:52]}")
con.close()
