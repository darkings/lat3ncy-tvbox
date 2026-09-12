#!/usr/bin/env python3
"""23:00 轮全面验证。"""

import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

d = json.load(
    open("/opt/ponyo-source-manager/reports/pipeline-run-20260809230001-1c3f88.json")
)
print("run:", d["run_id"], "timeslot:", d["timeslot"])
print("started:", d["started_at"], "finished:", d["finished_at"])
print("summary:", d["summary"])
for s in d["stages"]:
    dur = (s.get("duration_ms") or 0) // 1000
    err = str(s.get("error") or "")[:70]
    print(f"  {s['name']:<26} {s['status']:<7} {dur:>6}s  {err}")

print("\n== allow ==")
con = sqlite3.connect("/opt/ponyo-source-manager/data/sources.db")
rows = con.execute(
    "SELECT l.updated_at, r.name FROM list_state l "
    "JOIN norm_source n ON l.fingerprint=n.fingerprint "
    "JOIN raw_source r ON n.raw_id=r.id WHERE l.state='allow' ORDER BY l.updated_at"
).fetchall()
print(f"总数: {len(rows)}")
for r in rows:
    print(f"  {r[0][:16]}  {r[1][:24]}")

print("\n== 高分源时段覆盖（最新）==")
for kw in ["奶子", "爱坤", "360┃", "66-360", "如意"]:
    fps = con.execute(
        "SELECT DISTINCT n.fingerprint FROM norm_source n JOIN raw_source r ON n.raw_id=r.id WHERE r.name LIKE ?",
        (f"%{kw}%",),
    ).fetchall()
    for (fp,) in fps[:1]:
        slots = con.execute(
            "SELECT DISTINCT timeslot FROM conn_probe WHERE fingerprint=? AND ok=1 ORDER BY timeslot",
            (fp,),
        ).fetchall()
        print(f"  {kw}: {[s[0] for s in slots]}")

print("\n== live 状态 ==")
try:
    lr = json.load(open("/opt/ponyo-source-manager/reports/live-report.json"))
    print("generated:", lr.get("generated_at"))
    print("official:", lr.get("summary", {}).get("official_key"))
    for c in lr.get("candidates", []):
        if c.get("key") in ("live_migu", "live_sctv"):
            print(
                f"  {c.get('key')}: score={c.get('total_score')} validity={c.get('validity_rate')} hard={c.get('hard_pass')}"
            )
except Exception as e:
    print("live ERR", e)
con.close()
