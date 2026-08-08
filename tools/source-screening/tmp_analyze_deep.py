#!/usr/bin/env python3
"""20:00 轮深入分析：collector ssrf / probe_conn / 4 新源 / live 评估。"""

import json
import sqlite3
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect("/opt/ponyo-source-manager/data/sources.db")

print("== 1. maccms_collector 8s 全 ssrf ==")
try:
    d = json.load(
        open("/opt/ponyo-source-manager/reports/maccms-discovery-report.json")
    )
    print("generated_at:", d.get("generated_at"), "queued:", d.get("queued"))
    res = d.get("results", [])
    print(
        "结果:",
        len(res),
        "ssrf:",
        sum(1 for r in res if r.get("failure_stage") == "ssrf"),
    )
    for r in res[:8]:
        print("  ", r.get("endpoint", "")[:60], r.get("failure_stage"))
except Exception as e:
    print("ERR", e)

print("\n== 2. probe_conn 本轮 ==")
rows = con.execute(
    "SELECT COUNT(*), SUM(ok), SUM(dns_ok), SUM(tcp_ok) FROM conn_probe WHERE probed_at >= '2026-08-07T12:00:00+00:00'"
).fetchone()
print("URL 数:", rows[0], "ok:", rows[1], "dns_ok:", rows[2], "tcp_ok:", rows[3])
t = con.execute(
    "SELECT timeslot, COUNT(*) FROM conn_probe WHERE probed_at >= '2026-08-07T12:00:00+00:00' GROUP BY timeslot"
).fetchall()
print("timeslot 分布:", t)

print("\n== 3. 4 个新源覆盖情况 ==")
for h in ["yhzy.cc", "suboziyuan.net", "zy.xiaomaomi.cc", "api.maoyanapi.top"]:
    c = con.execute(
        "SELECT target_url, timeslot, ok, latency_ms, probed_at FROM conn_probe WHERE target_url LIKE ? ORDER BY probed_at DESC LIMIT 1",
        (f"%{h}%",),
    ).fetchone()
    print(f"  {h}: conn={c}")
    m = con.execute(
        "SELECT endpoint, search_ok, failure_stage FROM maccms_probe_result WHERE endpoint LIKE ? ORDER BY probed_at DESC LIMIT 1",
        (f"%{h}%",),
    ).fetchone()
    print(f"      maccms={m}")

print("\n== 4. live 评估 ==")
try:
    lr = json.load(open("/opt/ponyo-source-manager/reports/live-report.json"))
    print("generated_at:", lr.get("generated_at"))
    for c in lr.get("candidates", []):
        print(
            f"  {c.get('name', '?'):<12} score={c.get('total_score')} validity={c.get('validity_rate')} latency={c.get('avg_latency_ms')}ms hard_pass={c.get('hard_pass')}"
        )
except Exception as e:
    print("ERR", e)

print("\n== 5. materialize 错误 ==")
d = json.load(
    open("/opt/ponyo-source-manager/reports/pipeline-run-20260807200001-d9c6d6.json")
)
for s in d["stages"]:
    if s["name"] in ("materialize_approved_assets", "release"):
        print(s["name"], s["status"])
        print("  error:", str(s.get("error"))[:300])
        print("  output:", str(s.get("output"))[:300])

con.close()
