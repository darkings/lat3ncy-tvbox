#!/usr/bin/env python3
"""检查 live 选举状态。"""

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

try:
    d = json.load(open("/opt/ponyo-source-manager/reports/live-report.json"))
    print("live generated:", d.get("generated_at"))
    for c in d.get("candidates", []):
        if c.get("hard_pass") or c.get("total_score", 0) > 50:
            print(
                f"  {str(c.get('name'))[:16]:<18} score={c.get('total_score')} validity={c.get('validity_rate')} hard={c.get('hard_pass')} key={c.get('key')}"
            )
    print("\nsummary:", json.dumps(d.get("summary", {}), ensure_ascii=False)[:300])
except Exception as e:
    print("ERR", e)

# 库里正式直播源的标记
import sqlite3

con = sqlite3.connect("/opt/ponyo-source-manager/data/sources.db")
try:
    rows = con.execute(
        "SELECT fingerprint, state, reason FROM list_state WHERE state='allow' AND (reason LIKE '%直播%' OR reason LIKE '%live%')"
    ).fetchall()
    print("\n直播 allow:", rows[:5])
except Exception as e:
    print("直播 allow 查询:", e)
con.close()
