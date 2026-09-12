#!/usr/bin/env python3
"""分析 13:00 轮 run 报告。"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

d = json.load(open("/opt/ponyo-source-manager/reports/pipeline-run-20260808130001-ee4c06.json"))
print("run:", d["run_id"], "timeslot:", d["timeslot"])
print("started:", d["started_at"], "finished:", d["finished_at"])
print("summary:", d["summary"])
print()
for s in d["stages"]:
    dur = (s.get("duration_ms") or 0) // 1000
    err = str(s.get("error") or "")[:100]
    print(f"{s['name']:<28} {s['status']:<7} {dur:>6}s  {err}")
