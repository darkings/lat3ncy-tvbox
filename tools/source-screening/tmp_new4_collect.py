#!/usr/bin/env python3
"""直接用 MacCMSCollector 探测 4 个新源（绕过 main 的截断）。"""

import json
import sys
import uuid

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "/opt/ponyo-source-manager/src")

from ponyo_source_manager.discovery.maccms_collector import MacCMSCollector

ENDPOINTS = [
    "https://yhzy.cc/api.php/provide/vod/",
    "http://suboziyuan.net/api.php/provide/vod/",
    "https://zy.xiaomaomi.cc/api.php/provide/vod/",
    "https://api.maoyanapi.top/api.php/provide/vod/at/json",
]

collector = MacCMSCollector("/opt/ponyo-source-manager/data/sources.db")
run_id = uuid.uuid4().hex
results = []
for ep in ENDPOINTS:
    r = collector.probe_endpoint(ep, run_id=run_id)
    results.append(r)
    print(f"{ep[:45]:<48} passed={r['passed']} stage={r['failure_stage']}")
    for p in r.get("probes", []):
        print(
            f"    kw={p.get('keyword')} search={p.get('search_ok')} hit={p.get('keyword_hit')} detail={p.get('detail_ok')} playable={p.get('playable_url_count')}"
        )

with open("/tmp/new4-collector.json", "w", encoding="utf-8") as f:
    json.dump({"run_id": run_id, "results": results}, f, ensure_ascii=False, indent=1)
