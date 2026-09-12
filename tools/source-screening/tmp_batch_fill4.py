#!/usr/bin/env python3
"""对缺时段高分源跑齐 4 时段强制探测。"""

import sqlite3
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect("/opt/ponyo-source-manager/data/sources.db")

TARGETS = [
    "☀飞龙🔹秒播",
    "35-最大",
    "25-最大",
    "49-无忧",
    "1-艾旦",
    "21-爱胆",
    "lovedan.net┃GH",
    "360ZZ┃GH",
    "🎬飘零资源",
    "鸡坤资源",
]
fps = []
for name in TARGETS:
    row = con.execute(
        "SELECT n.fingerprint FROM norm_source n JOIN raw_source r ON n.raw_id=r.id WHERE r.name=? LIMIT 1",
        (name,),
    ).fetchone()
    if row:
        fps.append(row[0])
print(f"目标指纹: {len(fps)}")

for ts in ("morning", "noon", "evening", "night"):
    args = [
        "/opt/ponyo-source-manager/.venv/bin/python",
        "-m",
        "ponyo_source_manager.probes.probe_conn",
        "--timeslot",
        ts,
        "--max-age-hours",
        "0",
        "--fail-cool-hours",
        "0",
    ]
    for fp in fps:
        args += ["--fingerprint", fp]
    args += ["--report", f"/tmp/high_fill_{ts}.json"]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=1200)
        print(f"[{ts}] {r.stdout.strip()[-130:]}")
    except Exception as e:
        print(f"[{ts}] ERR {e}")
con.close()
