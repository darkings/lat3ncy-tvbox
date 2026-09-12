#!/usr/bin/env python3
"""每日候选池测速：只测 live_candidates.json，不重写整合源。

规则（与用户确认）：
  - fetch_failed（拉取失败）      -> 从候选池删除
  - 能拉到但 hard_pass=False      -> 保留，enabled=false（观察一轮）
  - hard_pass=True                -> 保留，enabled=true，写入测速指标
  - 不触碰 subscription/aggregated-live.m3u（由每日 aggregate_live.py 负责）
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ponyo_source_manager.core.common import CONFIG_DIR, REPORT_DIR
from ponyo_source_manager.probes.live import (
    evaluate_live_source,
    load_configured_live_candidates,
    load_test_channels,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    p = argparse.ArgumentParser(description="每日候选池测速")
    p.add_argument("--config", default=None, help="live_candidates.json 路径")
    p.add_argument("--report", default=None, help="测速报告输出路径")
    p.add_argument("--dry-run", action="store_true", help="只测速，不写回配置")
    args = p.parse_args()

    config_path = Path(args.config) if args.config else CONFIG_DIR / "live_candidates.json"
    report_path = (
        Path(args.report)
        if args.report
        else REPORT_DIR / "live-candidates-probe.json"
    )

    candidates = load_configured_live_candidates(config_path)
    test_channels = load_test_channels()

    print(f"=== 候选池每日测速 ===")
    print(f"候选源: {len(candidates)} 个, 测试频道: {len(test_channels)} 个\n")

    kept: list[dict] = []
    report_rows: list[dict] = []

    for c in candidates:
        key = str(c.get("key", "")).strip()
        name = str(c.get("name", "")).strip()
        url = str(c.get("url", "")).strip()
        if not url:
            print(f"[删除] {name or key}: 无 url")
            continue

        print(f"测速 {name} ({key}) ...")
        try:
            res = evaluate_live_source(key, url, test_channels)
        except Exception as e:  # 评估异常视同拉取失败 -> 删除
            print(f"  [删除] 评估异常: {e}")
            report_rows.append({"key": key, "name": name, "url": url,
                                "action": "deleted", "reason": f"exception:{e}"})
            continue

        reject = res.get("reject_reason")
        hard_pass = bool(res.get("hard_pass"))
        score = res.get("total_score", 0.0)
        validity = res.get("validity_rate", 0.0)
        latency = res.get("avg_latency_ms", 9999)

        if reject == "fetch_failed":
            # 拉取失败 -> 直接删除
            print(f"  [删除] 拉取失败")
            report_rows.append({"key": key, "name": name, "url": url,
                                "action": "deleted", "reason": "fetch_failed"})
            continue

        # 能拉到：保留；按 hard_pass 决定 enabled
        enabled = hard_pass
        entry = {
            "key": key,
            "name": name,
            "url": url,
            "enabled": enabled,
            "score": score,
            "validity_rate": validity,
            "avg_latency_ms": latency,
            "last_probed": _now(),
        }
        kept.append(entry)

        action = "enabled" if enabled else "disabled"
        print(f"  [{'启用' if enabled else '禁用观察'}] score={score} "
              f"validity={validity:.2%} latency={latency}ms reject={reject}")
        report_rows.append({"key": key, "name": name, "url": url,
                            "action": action, "reason": reject,
                            "score": score, "validity_rate": validity,
                            "avg_latency_ms": latency, "hard_pass": hard_pass})

    # 按 score 降序（高分在前）
    kept.sort(key=lambda x: x.get("score", 0), reverse=True)

    if not args.dry_run:
        config_path.write_text(
            json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n已写回 {config_path}: 保留 {len(kept)} / {len(candidates)}")
    else:
        print(f"\n[dry-run] 不写回。将保留 {len(kept)} / {len(candidates)}")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps({"probed_at": _now(), "total": len(candidates),
                    "kept": len(kept), "rows": report_rows},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"报告: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

