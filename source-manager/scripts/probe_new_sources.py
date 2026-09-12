#!/usr/bin/env python3
"""对预检通过的新直播源做深度测速(evaluate_live_source)。

只测速、打印结论、写报告；默认不写回 live_candidates.json。
--apply 才会把 hard_pass=True 的源追加进候选池。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ponyo_source_manager.core.common import CONFIG_DIR, REPORT_DIR
from ponyo_source_manager.probes.live import evaluate_live_source, load_test_channels

# 预检通过、值得深度测速的新源（key, name, url）
NEW_SOURCES = [
    ("iptv_org_cn", "IPTV-Org 中国",
     "https://cdn.jsdelivr.net/gh/iptv-org/iptv@master/streams/cn.m3u"),
    ("iptv_org_cctv", "IPTV-Org CCTV",
     "https://cdn.jsdelivr.net/gh/iptv-org/iptv@master/streams/cn_cctv.m3u"),
    ("fanmingming_ipv6", "范明明IPv6",
     "https://cdn.jsdelivr.net/gh/fanmingming/live@main/tv/m3u/ipv6.m3u"),
]


def main() -> int:
    p = argparse.ArgumentParser(description="新直播源深度测速")
    p.add_argument("--report", default=str(REPORT_DIR / "live-new-sources-probe.json"))
    p.add_argument("--apply", action="store_true",
                   help="把 hard_pass 的源写回 live_candidates.json")
    p.add_argument("--config", default=str(CONFIG_DIR / "live_candidates.json"))
    args = p.parse_args()

    test_channels = load_test_channels()
    print(f"=== 新源深度测速 ===  候选新源: {len(NEW_SOURCES)}, 测试频道: {len(test_channels)}\n")

    results = []
    for key, name, url in NEW_SOURCES:
        print(f"测速 {name} ({key}) ...")
        try:
            res = evaluate_live_source(key, url, test_channels)
        except Exception as e:
            print(f"  [异常] {e}")
            results.append({"key": key, "name": name, "url": url,
                            "hard_pass": False, "error": str(e)})
            continue
        hp = res["hard_pass"]
        print(f"  score={res['total_score']} validity={res['validity_rate']:.2%} "
              f"latency={res['avg_latency_ms']}ms reject={res['reject_reason']} "
              f"-> {'✅ hard_pass' if hp else '❌ 未通过'}")
        results.append({"key": key, "name": name, "url": url,
                        "hard_pass": hp, "score": res["total_score"],
                        "validity_rate": res["validity_rate"],
                        "avg_latency_ms": res["avg_latency_ms"],
                        "reject_reason": res["reject_reason"]})

    passed = [r for r in results if r.get("hard_pass")]
    print(f"\n=== 通过 hard_pass: {len(passed)} / {len(results)} ===")
    for r in passed:
        print(f"  {r['name']}: score={r['score']} validity={r['validity_rate']:.2%}")

    if args.apply and passed:
        cfg = Path(args.config)
        existing = json.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else []
        existing_keys = {c.get("key") for c in existing}
        added = 0
        for r in passed:
            if r["key"] not in existing_keys:
                existing.append({"key": r["key"], "name": r["name"], "url": r["url"],
                                 "enabled": True, "score": r["score"],
                                 "validity_rate": r["validity_rate"],
                                 "avg_latency_ms": r["avg_latency_ms"],
                                 "last_probed": datetime.now(timezone.utc).isoformat()})
                added += 1
        existing.sort(key=lambda x: x.get("score", 0), reverse=True)
        cfg.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[apply] 已写入 {cfg}: 新增 {added} 个, 共 {len(existing)} 个")
    elif not args.apply:
        print("\n(未加 --apply，不写回候选池)")

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(
        {"probed_at": datetime.now(timezone.utc).isoformat(),
         "passed": len(passed), "rows": results}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"报告: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
