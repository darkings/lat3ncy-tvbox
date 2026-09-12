#!/usr/bin/env python3
"""验证三轮（08/13/20）运行结果。"""

import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

import glob
import os

files = sorted(
    glob.glob("/opt/ponyo-source-manager/reports/pipeline-run-20260809*.json")
)
print(f"今日 run 报告: {len(files)}")
for f in files:
    d = json.load(open(f))
    print(f"\n== {d['run_id']} timeslot={d['timeslot']} ==")
    print(f"  时长: {(d['finished_at'])}")
    for s in d["stages"]:
        dur = (s.get("duration_ms") or 0) // 1000
        err = str(s.get("error") or "")[:60]
        print(f"  {s['name']:<26} {s['status']:<7} {dur:>6}s  {err}")

# allow 状态
print("\n== 当前 allow ==")
con = sqlite3.connect("/opt/ponyo-source-manager/data/sources.db")
rows = con.execute(
    "SELECT l.updated_at, r.name, r.api FROM list_state l "
    "JOIN norm_source n ON l.fingerprint=n.fingerprint "
    "JOIN raw_source r ON n.raw_id=r.id WHERE l.state='allow' ORDER BY l.updated_at"
).fetchall()
print(f"allow 总数: {len(rows)}")
for r in rows:
    print(f"  {r[0][:16]}  {r[1][:22]:<24} {r[2][:50]}")

# 高分源时段覆盖
print("\n== 高分源时段覆盖 ==")
for kw in ["奶子", "爱坤", "360", "橘猫", "如意"]:
    fps = con.execute(
        "SELECT DISTINCT n.fingerprint FROM norm_source n JOIN raw_source r ON n.raw_id=r.id WHERE r.name LIKE ?",
        (f"%{kw}%",),
    ).fetchall()
    for (fp,) in fps[:1]:
        slots = con.execute(
            "SELECT DISTINCT timeslot FROM conn_probe WHERE fingerprint=? AND ok=1 ORDER BY timeslot",
            (fp,),
        ).fetchall()
        st = [s[0] for s in slots]
        print(f"  {kw}: {st}")
con.close()
