#!/usr/bin/env python3
"""轻量发现新直播源：只拉取+预检分析，不逐频道深度测速，不写回。

用于快速摸清各候选仓库现状（频道数/中国频道/是否被预检拒绝），
把"值得深度测速"的仓库筛出来。深度测速交给 probe/aggregate 流程。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from ponyo_source_manager.core.common import REPORT_DIR
from ponyo_source_manager.discovery.live_discovery import (
    LIVE_SOURCE_REPOS,
    fetch_live_list,
    analyze_live_content,
)


def main() -> int:
    p = argparse.ArgumentParser(description="轻量发现新直播源(只预检)")
    p.add_argument("--report", default=str(REPORT_DIR / "live-discover-scan.json"))
    args = p.parse_args()

    print(f"=== 直播源发现(轻量预检) ===")
    print(f"仓库数: {len(LIVE_SOURCE_REPOS)}\n")

    rows = []
    for repo, branch, path, name, key_prefix in LIVE_SOURCE_REPOS:
        url = f"https://cdn.jsdelivr.net/gh/{repo}@{branch}/{path}"
        print(f"扫描 {name}  ({repo}/{path})")
        try:
            content = fetch_live_list(repo, branch, path)
        except Exception as e:
            print(f"  [拉取异常] {e}")
            rows.append({"key": key_prefix, "name": name, "url": url,
                         "ok": False, "reason": f"exception:{e}"})
            continue
        if not content:
            print(f"  [拉取失败]")
            rows.append({"key": key_prefix, "name": name, "url": url,
                         "ok": False, "reason": "fetch_failed"})
            continue

        stats = analyze_live_content(content, name)
        reject = stats["reject_reason"]
        tag = "拒绝" if reject else "待测速"
        print(f"  频道 总={stats['total_channels']} 去重={stats['unique_channels']} "
              f"中国={stats['china_channels']}  预检={reject or '通过'} -> [{tag}]")
        rows.append({"key": key_prefix, "name": name, "url": url, "ok": not reject,
                     "reason": reject, "total_channels": stats["total_channels"],
                     "unique_channels": stats["unique_channels"],
                     "china_channels": stats["china_channels"]})

    passed = [r for r in rows if r.get("ok")]
    print(f"\n=== 预检通过 {len(passed)} / {len(rows)} ===")
    for r in passed:
        print(f"  {r['name']}: 中国频道 {r['china_channels']}, 总 {r['total_channels']}")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    Path_write = args.report
    with open(Path_write, "w", encoding="utf-8") as f:
        json.dump({"scanned_at": datetime.now(timezone.utc).isoformat(),
                   "total": len(rows), "passed": len(passed), "rows": rows},
                  f, ensure_ascii=False, indent=2)
    print(f"\n报告: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
