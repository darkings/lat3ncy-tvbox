#!/usr/bin/env python3
"""高分源最新评分状态。"""

import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect("/opt/ponyo-source-manager/data/sources.db")

rows = con.execute(
    "SELECT s.fingerprint, s.total_score, s.hard_pass, s.scored_at, r.name, r.api "
    "FROM score_snapshot s JOIN norm_source n ON s.fingerprint=n.fingerprint "
    "JOIN raw_source r ON n.raw_id=r.id "
    "WHERE s.total_score > 85 "
    "AND s.scored_at = (SELECT MAX(s2.scored_at) FROM score_snapshot s2 WHERE s2.fingerprint=s.fingerprint) "
    "ORDER BY s.total_score DESC LIMIT 12"
).fetchall()
print(f"高分源（最新评分>85）: {len(rows)}")
for r in rows:
    print(f"  {r[1]:<7} hard={r[2]} {r[3][:16]}  {r[4][:20]:<22} {r[5][:45]}")

# 奶子/爱坤/360 时段覆盖
print("\n== 关键源时段覆盖 ==")
for kw in ["奶子", "爱坤", "360", "飘零", "橘猫"]:
    fps = con.execute(
        "SELECT DISTINCT n.fingerprint FROM norm_source n JOIN raw_source r ON n.raw_id=r.id WHERE r.name LIKE ?",
        (f"%{kw}%",),
    ).fetchall()
    for (fp,) in fps[:2]:
        slots = con.execute(
            "SELECT DISTINCT timeslot FROM conn_probe WHERE fingerprint=? AND ok=1 ORDER BY timeslot",
            (fp,),
        ).fetchall()
        st = [s[0] for s in slots]
        print(f"  {kw}: {st}")
con.close()
