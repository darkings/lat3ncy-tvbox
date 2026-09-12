#!/usr/bin/env python3
"""hard_pass 现状分析。"""

import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect("/opt/ponyo-source-manager/data/sources.db")

# 最新评分中 hard_pass=1 的源
rows = con.execute(
    "SELECT s.fingerprint, s.total_score, s.hard_pass, s.scored_at, r.name, r.api "
    "FROM score_snapshot s JOIN norm_source n ON s.fingerprint=n.fingerprint "
    "JOIN raw_source r ON n.raw_id=r.id "
    "WHERE s.scored_at = (SELECT MAX(s2.scored_at) FROM score_snapshot s2 WHERE s2.fingerprint=s.fingerprint) "
    "ORDER BY s.total_score DESC"
).fetchall()
hard = [r for r in rows if r[2] == 1]
print(f"最新评分总数: {len(rows)}")
print(f"hard_pass=1: {len(hard)}")
for r in hard[:20]:
    slots = con.execute(
        "SELECT COUNT(DISTINCT timeslot) FROM conn_probe WHERE fingerprint=? AND ok=1",
        (r[0],),
    ).fetchone()[0]
    print(f"  {r[1]:<7} hard={r[2]} 时段={slots}/4  {r[4][:18]:<20} {r[5][:45]}")

# 高分但 hard=0 的（接近解锁）
print("\n== 高分但 hard=0（>90 分）==")
for r in rows:
    if r[2] == 0 and r[1] > 90:
        slots = con.execute(
            "SELECT DISTINCT timeslot FROM conn_probe WHERE fingerprint=? AND ok=1",
            (r[0],),
        ).fetchall()
        print(f"  {r[1]:<7} {[s[0] for s in slots]}  {r[4][:18]:<20} {r[5][:45]}")

con.close()
