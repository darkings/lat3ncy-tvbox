#!/usr/bin/env python3
"""检查咪咕/四川电信候选详情。"""

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

d = json.load(open("/opt/ponyo-source-manager/reports/live-report.json"))
for c in d.get("candidates", []):
    if c.get("key") in ("live_migu", "live_sctv", "live_aptv", "live_qist_ipv6"):
        print(f"key={c.get('key')}")
        print(
            f"  score={c.get('total_score')} validity={c.get('validity_rate')} latency={c.get('avg_latency_ms')} hard={c.get('hard_pass')}"
        )
        print(f"  metadata={json.dumps(c.get('metadata'), ensure_ascii=False)[:150]}")
        for pc in (c.get("probed_channels") or [])[:4]:
            print(
                f"    {pc.get('channel')}: ok={pc.get('ok')} latency={pc.get('latency_ms')}"
            )

# 咪咕列表可访问性
import urllib.request

try:
    r = urllib.request.urlopen(
        urllib.request.Request(
            "https://develop202.github.io/migu_video/interface.txt",
            headers={"User-Agent": "Mozilla/5.0"},
        ),
        timeout=15,
    )
    body = r.read()
    print(f"\n咪咕列表直连: {r.status} {len(body)}B")
except Exception as e:
    print(f"\n咪咕列表直连: {type(e).__name__} {e}")
