#!/usr/bin/env python3
"""分析：4时段全但 hard=0 源的失败维度 + 缺时段源清单。"""

import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect("/opt/ponyo-source-manager/data/sources.db")

cols = [c[1] for c in con.execute("PRAGMA table_info(score_snapshot)").fetchall()]
print("score_snapshot 列:", cols)

# 4 时段全但 hard=0 的 >90 分源：看各分项
rows = con.execute(
    "SELECT s.fingerprint, s.total_score, s.play_success, s.stability, s.speed_score, "
    "s.func_score, s.quality_score, s.hard_pass, s.scored_at, r.name "
    "FROM score_snapshot s JOIN norm_source n ON s.fingerprint=n.fingerprint "
    "JOIN raw_source r ON n.raw_id=r.id "
    "WHERE s.scored_at = (SELECT MAX(s2.scored_at) FROM score_snapshot s2 WHERE s2.fingerprint=s.fingerprint) "
    "AND s.total_score > 90 AND s.hard_pass = 0 "
    "AND s.fingerprint IN (SELECT fingerprint FROM conn_probe WHERE ok=1 GROUP BY fingerprint HAVING COUNT(DISTINCT timeslot)=4) "
    "ORDER BY s.total_score DESC LIMIT 10"
).fetchall()
print("\n== 4时段全但 hard=0（>90分）失败维度 ==")
for r in rows:
    print(
        f"  {r[9][:14]:<16} total={r[1]:<6} play={r[2]:<5} stab={r[3]:<5} speed={r[4]:<5} "
        f"func={r[5]:<5} quality={r[6]:<5} {r[8][:16]}"
    )

# 缺时段的高分源清单（可补测）
print("\n== 缺时段高分源（可手动补测）==")
rows2 = con.execute(
    "SELECT s.fingerprint, s.total_score, r.name, r.api "
    "FROM score_snapshot s JOIN norm_source n ON s.fingerprint=n.fingerprint "
    "JOIN raw_source r ON n.raw_id=r.id "
    "WHERE s.scored_at = (SELECT MAX(s2.scored_at) FROM score_snapshot s2 WHERE s2.fingerprint=s.fingerprint) "
    "AND s.total_score > 90 ORDER BY s.total_score DESC LIMIT 25"
).fetchall()
for fp, score, name, api in rows2:
    slots = con.execute(
        "SELECT DISTINCT timeslot FROM conn_probe WHERE fingerprint=? AND ok=1", (fp,)
    ).fetchall()
    st = sorted(s[0] for s in slots)
    missing = [t for t in ("morning", "noon", "evening", "night") if t not in st]
    if missing:
        print(f"  {score:<6} {str(name)[:16]:<18} 缺{missing}  {str(api)[:40]}")
con.close()
