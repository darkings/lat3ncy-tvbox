#!/usr/bin/env python3
"""验证 night 时段数据 + 奶子/爱坤解锁状态。"""

import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect("/opt/ponyo-source-manager/data/sources.db")

# night 时段 conn 数据
rows = con.execute(
    "SELECT COUNT(*), SUM(ok) FROM conn_probe WHERE timeslot='night' AND probed_at >= '2026-08-08T15:00:00+00:00'"
).fetchone()
print(f"23:00轮 night conn_probe: {rows[0]} 条, ok={rows[1]}")

# 各源 night 覆盖
rows2 = con.execute(
    "SELECT COUNT(DISTINCT fingerprint) FROM conn_probe WHERE timeslot='night' AND probed_at >= '2026-08-08T15:00:00+00:00'"
).fetchone()
print(f"覆盖指纹数: {rows2[0]}")

# 奶子/爱坤/360 等高分源的状态
print("\n== 高分源评分状态 ==")
high = con.execute(
    "SELECT s.fingerprint, s.score, s.timeslots_covered, s.hard_pass, r.name "
    "FROM score_snapshot s JOIN norm_source n ON s.fingerprint=n.fingerprint "
    "JOIN raw_source r ON n.raw_id=r.id "
    "WHERE s.score > 90 ORDER BY s.score DESC LIMIT 8"
).fetchall()
cols = [c[1] for c in con.execute("PRAGMA table_info(score_snapshot)").fetchall()]
print("score_snapshot 列:", cols[:12])
for r in high:
    print(" ", r)
con.close()
