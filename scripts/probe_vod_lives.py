#!/usr/bin/env python3
"""对筛查有效的直播源(来自点播挖掘)做深度测速，hard_pass 可写回候选池。

流程: 读 lives-screened.json 有效项 -> 按真实源去重 -> 源级并行 evaluate_live_source
-> hard_pass=True 的源, --apply 时追加进 live_candidates.json。

分辨率权重: evaluate_live_source 内部已按实测分辨率(m3u8清单+ffprobe兜底)对
清晰度分加权(见 live.py 的 _height_to_frac)。
"""

from __future__ import annotations

import argparse
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from ponyo_source_manager.core.common import CONFIG_DIR, REPORT_DIR
from ponyo_source_manager.probes.live import evaluate_live_source, load_test_channels

PROXY = ["https://gh.927223.xyz/","https://ghfast.top/","https://gh-proxy.com/",
         "https://github.moeyy.xyz/","https://ghproxy.net/","https://mirror.ghproxy.com/",
         "https://raw.kkgithub.com/","https://down.nigx.cn/","https://fastgit.cc/",
         "https://gh-proxy.org/","https://cdn.gh-proxy.org/","https://gh.tryxd.cn/",
         "https://raw.gitmirror.com/","https://ghproxy.com/","https://gh.halonice.com/"]

_print_lock = threading.Lock()


def real(u: str) -> str:
    for p in PROXY:
        if u.startswith(p):
            return u[len(p):]
    return u


def dedup(valid: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for r in valid:
        ru = real(r["url"])
        if ru not in best or r.get("china_channels", 0) > best[ru].get("china_channels", 0):
            best[ru] = r
    out = list(best.values())
    out.sort(key=lambda x: x.get("china_channels", 0), reverse=True)
    return out


def probe_one(idx: int, total: int, item: dict, test_channels: list[str]) -> dict:
    name, url = item["name"], item["url"]
    try:
        res = evaluate_live_source(name, url, test_channels)
        hp = res["hard_pass"]
        out = {"name": name, "url": url, "hard_pass": hp,
               "score": res["total_score"], "validity_rate": res["validity_rate"],
               "avg_latency_ms": res["avg_latency_ms"],
               "reject_reason": res["reject_reason"],
               "china_channels": item.get("china_channels")}
        with _print_lock:
            print(f"[{idx}/{total}] {name[:16]:16} score={res['total_score']:>6} "
                  f"validity={res['validity_rate']:.2%} lat={res['avg_latency_ms']:>5}ms "
                  f"reject={res['reject_reason']} -> {'PASS' if hp else 'fail'}", flush=True)
        return out
    except Exception as e:
        with _print_lock:
            print(f"[{idx}/{total}] {name[:16]:16} [异常] {e}", flush=True)
        return {"name": name, "url": url, "hard_pass": False, "error": str(e),
                "china_channels": item.get("china_channels")}


def main() -> int:
    p = argparse.ArgumentParser(description="点播挖掘直播源-深度测速(并行)")
    p.add_argument("--input", default=str(REPORT_DIR / "lives-screened.json"))
    p.add_argument("--report", default=str(REPORT_DIR / "lives-vod-probe.json"))
    p.add_argument("--config", default=str(CONFIG_DIR / "live_candidates.json"))
    p.add_argument("--apply", action="store_true", help="hard_pass 写回候选池")
    p.add_argument("--min-china", type=int, default=30, help="只测中国频道>=N 的源")
    p.add_argument("--limit", type=int, default=0, help="只测前 N 个源(0=全部)")
    p.add_argument("--workers", type=int, default=10, help="源级并行数")
    args = p.parse_args()

    data = json.load(open(args.input, encoding="utf-8"))
    valid = dedup(data["valid_entries"])
    targets = [r for r in valid if r.get("china_channels", 0) >= args.min_china]
    if args.limit > 0:
        targets = targets[: args.limit]
    test_channels = load_test_channels()

    print(f"=== 点播挖掘源深度测速(并行 workers={args.workers}) ===")
    print(f"去重后 {len(valid)} 个, 中国频道>={args.min_china} 的 {len(targets)} 个, 测试频道 {len(test_channels)}\n", flush=True)

    total = len(targets)
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(probe_one, i, total, it, test_channels)
                for i, it in enumerate(targets, 1)]
        for fut in as_completed(futs):
            results.append(fut.result())

    passed = [r for r in results if r.get("hard_pass")]
    print(f"\n=== hard_pass: {len(passed)} / {len(results)} ===", flush=True)
    for r in sorted(passed, key=lambda x: -x.get("score", 0)):
        print(f"  PASS {r['name'][:16]:16} score={r['score']} validity={r['validity_rate']:.2%} {r['url'][:55]}")

    if args.apply and passed:
        cfg = Path(args.config)
        existing = json.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else []
        existing_keys = {c.get("key") for c in existing}
        existing_urls = {c.get("url") for c in existing}
        added = 0
        for r in sorted(passed, key=lambda x: -x.get("score", 0)):
            if r["url"] in existing_urls:
                continue
            key = "vod_" + re.sub(r"\W+", "_", r["name"])[:30]
            base, n = key, 2
            while key in existing_keys:
                key = f"{base}_{n}"; n += 1
            existing_keys.add(key)
            existing.append({"key": key, "name": r["name"], "url": r["url"], "enabled": True,
                             "score": r["score"], "validity_rate": r["validity_rate"],
                             "avg_latency_ms": r["avg_latency_ms"],
                             "last_probed": datetime.now(timezone.utc).isoformat()})
            added += 1
        existing.sort(key=lambda x: x.get("score", 0), reverse=True)
        cfg.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[apply] 新增 {added} 个 -> 候选池共 {len(existing)} 个")
    elif not args.apply:
        print("\n(未加 --apply, 不写回候选池)")

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(
        {"probed_at": datetime.now(timezone.utc).isoformat(),
         "tested": len(results), "passed": len(passed), "rows": results},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
