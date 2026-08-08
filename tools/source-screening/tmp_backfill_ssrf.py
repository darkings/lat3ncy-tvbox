#!/usr/bin/env python3
"""回填历史 ssrf 探测结果到 maccms_probe_result（旧代码不写库）。"""

import json
import sqlite3
import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")

DB = "/opt/ponyo-source-manager/data/sources.db"
REPORTS = [
    "/opt/ponyo-source-manager/reports/maccms-discovery-report.json",  # 20:00 轮
    "/tmp/maccms-manual-report.json",  # 手动轮
]

now = datetime.now(timezone.utc).isoformat()
con = sqlite3.connect(DB)
backfilled = 0
for rp in REPORTS:
    try:
        d = json.load(open(rp))
    except Exception as e:
        print(f"跳过 {rp}: {e}")
        continue
    run_id = d.get("run_id", "backfill")
    probed_at = d.get("generated_at", now)
    for r in d.get("results", []):
        ep = r.get("endpoint")
        stage = r.get("failure_stage")
        if not ep or stage != "ssrf":
            continue
        # 已有记录则跳过
        exists = con.execute(
            "SELECT 1 FROM maccms_probe_result WHERE endpoint=? AND failure_stage='ssrf' LIMIT 1",
            (ep,),
        ).fetchone()
        if exists:
            continue
        con.execute(
            "INSERT INTO maccms_probe_result "
            "(run_id, endpoint, keyword, search_ok, keyword_hit, detail_ok, "
            "playable_url_count, failure_stage, evidence_json, probed_at) "
            "VALUES (?, ?, '', 0, 0, 0, 0, 'ssrf', ?, ?)",
            (
                run_id,
                ep,
                json.dumps({"matched_name": None, "media_verified": False}),
                probed_at,
            ),
        )
        backfilled += 1
con.commit()
print(f"回填 ssrf 记录: {backfilled}")

# 验证排序
sys.path.insert(0, "/opt/ponyo-source-manager/src")
from ponyo_source_manager.discovery.maccms_collector import load_endpoints_from_db

eps = load_endpoints_from_db(DB)
print(f"队列总数: {len(eps)}")
print("前 30 个:")
for e in eps[:30]:
    print("  ", e[:70])
for h in ["yhzy.cc", "suboziyuan.net", "zy.xiaomaomi.cc", "maoyanapi"]:
    for i, e in enumerate(eps):
        if h in e:
            print(f"{h}: 队列第 {i} 位")
            break
con.close()
