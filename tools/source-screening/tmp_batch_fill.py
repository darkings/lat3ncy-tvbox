#!/usr/bin/env python3
"""补测缺时段高分源：查指纹 + 跑 probe_conn。"""

import sqlite3
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect("/opt/ponyo-source-manager/data/sources.db")

# 目标：缺时段的高分源（名字 + 缺的时段）
TARGETS = [
    ("☀飞龙🔹秒播", ["morning", "noon"]),
    ("35-最大", ["night"]),
    ("25-最大", ["night"]),
    ("49-无忧", ["night"]),
    ("1-艾旦", ["night"]),
    ("21-爱胆", ["night"]),
    ("lovedan.net┃GH", ["morning", "evening"]),
    ("360ZZ┃GH", ["morning", "evening"]),
    ("🎬飘零资源", ["noon", "evening", "night"]),
    ("鸡坤资源", ["noon"]),
]

fps = []
for name, missing in TARGETS:
    row = con.execute(
        "SELECT n.fingerprint, r.api FROM norm_source n JOIN raw_source r ON n.raw_id=r.id WHERE r.name=? LIMIT 1",
        (name,),
    ).fetchone()
    if row:
        fps.append(row[0])
        print(f"{name:<16} {row[1][:45]}")
    else:
        print(f"{name:<16} 未找到")

# 分批跑（每批 5 个指纹，避免一次太多）
args = [
    "/opt/ponyo-source-manager/.venv/bin/python",
    "-m",
    "ponyo_source_manager.probes.probe_conn",
    "--timeslot",
    "noon",
    "--max-age-hours",
    "0",
    "--fail-cool-hours",
    "0",
]
for fp in fps:
    args += ["--fingerprint", fp]
args += ["--report", "/tmp/high_fill.json"]
print("\n运行:", " ".join(args[:8]), "...")
r = subprocess.run(args, capture_output=True, text=True, timeout=900)
print(r.stdout[-200:])
if r.returncode != 0:
    print("ERR:", r.stderr[-300:])
con.close()
