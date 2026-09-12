#!/usr/bin/env python3
"""查补测 5 源的最新评分 + allow 变化。"""

import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect("/opt/ponyo-source-manager/data/sources.db")

fps = {
    "奶子": "c2f638574ccc361c14ab5d7d295dca5f40bc857ae7000f18c91925003ea9207f",
    "爱坤": "04228f4770bde3e9b4c6ee0b4fb1220ffd8128c45b5c3cfcde1da8fc8821becb",
    "10-如意": "bb468429cd63ab2ea92964495ab83281aaf0dc2aa50d843aa5847ce8d65b720c",
    "66-360": "6728cc8ee3d1b53c57469173664a6ed8221bddff099ed42741a5693742ee721c",
    "360┃": "a5643b7ad6979516589f6e3dd59a5e3c7905cadb13cab78fbcc9db924e00cd08",
}
print("== 补测 5 源最新评分 ==")
for name, fp in fps.items():
    r = con.execute(
        "SELECT total_score, play_success, stability, speed_score, func_score, quality_score, hard_pass, scored_at, consecutive_fail "
        "FROM score_snapshot WHERE fingerprint=? ORDER BY scored_at DESC LIMIT 1",
        (fp,),
    ).fetchone()
    if r:
        print(
            f"  {name:<8} total={r[0]:<6} play={r[1]:<5} stab={r[2]:<5} speed={r[3]:<6} "
            f"func={r[4]:<5} quality={r[5]:<6} hard={r[6]} fail={r[8]} {r[7][:16]}"
        )
    else:
        print(f"  {name}: 无评分")

print("\n== 最新评分 hard=1 全部 ==")
rows = con.execute(
    "SELECT s.total_score, r.name, s.scored_at FROM score_snapshot s "
    "JOIN norm_source n ON s.fingerprint=n.fingerprint JOIN raw_source r ON n.raw_id=r.id "
    "WHERE s.hard_pass=1 AND s.scored_at = (SELECT MAX(s2.scored_at) FROM score_snapshot s2 WHERE s2.fingerprint=s.fingerprint) "
    "ORDER BY s.total_score DESC"
).fetchall()
print(f"hard_pass=1: {len(rows)}")
for r in rows:
    print(f"  {r[0]:<7} {r[1][:20]:<22} {r[2][:16]}")

print("\n== allow 总数 ==")
n = con.execute("SELECT COUNT(*) FROM list_state WHERE state='allow'").fetchone()[0]
print(f"allow: {n}")
rows2 = con.execute(
    "SELECT l.updated_at, r.name FROM list_state l "
    "JOIN norm_source n ON l.fingerprint=n.fingerprint JOIN raw_source r ON n.raw_id=r.id "
    "WHERE l.state='allow' ORDER BY l.updated_at"
).fetchall()
for r in rows2[-5:]:
    print(f"  {r[0][:16]}  {r[1][:24]}")
con.close()
