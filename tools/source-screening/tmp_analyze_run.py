#!/usr/bin/env python3
"""分析 20:00 轮 run 报告。"""

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

d = json.load(
    open("/opt/ponyo-source-manager/reports/pipeline-run-20260807200001-d9c6d6.json")
)
print("run:", d["run_id"], "timeslot:", d["timeslot"])
print("started:", d["started_at"], "finished:", d["finished_at"])
print("summary:", d["summary"])
print()
for s in d["stages"]:
    out = s.get("output") or ""
    if isinstance(out, str) and len(out) > 130:
        out = out[:130] + "..."
    dur = (s.get("duration_ms") or 0) // 1000
    print(f"{s['name']:<28} {s['status']:<7} {dur:>6}s  {out}")
