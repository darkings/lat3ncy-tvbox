#!/usr/bin/env python3
"""单独评估 live_sctv 候选（复用 live.py 内部函数）。"""

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "/opt/ponyo-source-manager/src")

from ponyo_source_manager.core import net
from ponyo_source_manager.probes.live import (
    _normalize_channel_name,
    inspect_live_metadata,
    load_test_channels,
    parse_live_channel_routes,
    parse_live_channels,
    probe_live_channel,
)

URL = "https://cdn.jsdelivr.net/gh/darkings/lat3ncy-tvbox@main/subscription/sctv.m3u"
channels = load_test_channels()
print(f"测试频道: {channels}")

try:
    content = net.fetch_text(URL, timeout=15)
    mapping = parse_live_channels(content)
    routes = parse_live_channel_routes(content)
    metadata = inspect_live_metadata(content)
    print(f"列表解析: channels={len(mapping)} routes={len(routes)} metadata={metadata}")
except Exception as e:
    print(f"列表下载失败: {e}")
    sys.exit(1)

results = []
for ch in channels:
    target = mapping.get(_normalize_channel_name(ch))
    if target:
        res = probe_live_channel(target, timeout=8)
        results.append({"channel": ch, "url": target, **res})
        print(
            f"  {ch:<10} ok={res['ok']} latency={res.get('latency_ms')}ms err={res.get('err')}"
        )
    else:
        print(f"  {ch:<10} 无匹配")

valid = sum(1 for r in results if r["ok"] == 1)
rate = valid / len(results) if results else 0
print(f"\n有效率: {rate:.2f} ({valid}/{len(results)})")
with open("/tmp/live_sctv_eval.json", "w", encoding="utf-8") as f:
    json.dump(
        {"results": results, "validity_rate": rate, "metadata": metadata},
        f,
        ensure_ascii=False,
        indent=1,
    )
