#!/usr/bin/env python3
"""测试 collector 选中端点的 _getaddrinfo。"""

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "/opt/ponyo-source-manager/src")
from ponyo_source_manager.core import net

d = json.load(open("/tmp/maccms-manual-report.json"))
for r in d.get("results", [])[:30]:
    ep = r.get("endpoint", "")
    host = ep.split("/")[2] if "://" in ep else ep
    try:
        ok = net._getaddrinfo(host, 5.0)
    except Exception as e:
        ok = f"ERR {type(e).__name__}"
    print(f"{r.get('failure_stage', '?'):<8} {ok!s:<8} {host}")
