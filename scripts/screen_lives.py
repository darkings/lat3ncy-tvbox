#!/usr/bin/env python3
"""对 extract_lives_from_vod 提取的直播入口做快速筛查。

拉取每个入口 -> 解析频道数/中国频道 -> 预检(ipv6_only/carousel 等)。
不逐频道测速（快速）。输出可进入深度测速的有效候选列表。
"""

from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from ponyo_source_manager.core.common import REPORT_DIR
from ponyo_source_manager.core import net
from ponyo_source_manager.discovery.live_discovery import (
    fetch_live_list, analyze_live_content,
)

PROXY_PREFIXES = [
    "https://gh.927223.xyz/", "https://ghfast.top/", "https://gh-proxy.com/",
    "https://github.moeyy.xyz/", "https://ghproxy.net/", "https://mirror.ghproxy.com/",
    "https://raw.kkgithub.com/", "https://down.nigx.cn/", "https://fastgit.cc/",
    "https://gh-proxy.org/", "https://cdn.gh-proxy.org/", "https://gh.tryxd.cn/",
    "https://raw.gitmirror.com/", "https://ghproxy.com/",
]

GH_RE = re.compile(r"https?://(?:raw\.githubusercontent\.com|github\.com)/([^/]+)/([^/]+)/(?:raw/)?(?:refs/heads/)?([^/]+)/(.+)")


def real_url(u: str) -> str:
    for p in PROXY_PREFIXES:
        if u.startswith(p):
            return u[len(p):]
    return u


def fetch_entry(url: str, timeout: int) -> str | None:
    """拉取直播入口内容。GitHub 类 URL 走 jsDelivr 回退，其它直连。"""
    candidates = [url]
    ru = real_url(url)
    m = GH_RE.match(ru)
    if m:
        owner, repo, branch, path = m.groups()
        candidates = [
            f"https://cdn.jsdelivr.net/gh/{owner}/{repo}@{branch}/{path}",
            f"https://fastly.jsdelivr.net/gh/{owner}/{repo}@{branch}/{path}",
            url,
        ]
    for u in candidates:
        try:
            c = net.fetch_text(u, timeout=timeout, limiter=None)
            if c and len(c) > 30:
                return c
        except Exception:
            continue
    return None


def screen_one(idx: int, item: dict, timeout: int) -> dict:
    url = item["url"]
    name = item.get("name", "")
    content = fetch_entry(url, timeout)
    if not content:
        return {"idx": idx, "name": name, "url": url, "ok": False, "reason": "fetch_failed"}
    stats = analyze_live_content(content, name)
    reject = stats["reject_reason"]
    return {
        "idx": idx, "name": name, "url": url, "ok": not reject and stats["total_channels"] > 0,
        "reason": reject, "total_channels": stats["total_channels"],
        "unique_channels": stats["unique_channels"], "china_channels": stats["china_channels"],
    }


def main() -> int:
    p = argparse.ArgumentParser(description="筛查从点播提取的直播入口")
    p.add_argument("--input", default=str(REPORT_DIR / "lives-from-vod.json"))
    p.add_argument("--report", default=str(REPORT_DIR / "lives-screened.json"))
    p.add_argument("--workers", type=int, default=12)
    p.add_argument("--timeout", type=int, default=12)
    p.add_argument("--min-china", type=int, default=1, help="至少含 N 个中国频道才算有效")
    args = p.parse_args()

    data = json.load(open(args.input, encoding="utf-8"))
    lives = data["lives"]
    print(f"=== 筛查直播入口 ===  共 {len(lives)} 个, workers={args.workers}\n")

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(screen_one, i, it, args.timeout): i for i, it in enumerate(lives)}
        done = 0
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            done += 1
            tag = "OK" if r["ok"] else "×"
            print(f"[{done}/{len(lives)}] {tag} {r['name'][:14]:14} "
                  f"中={r.get('china_channels','-'):>4} 总={r.get('total_channels','-'):>5} "
                  f"{r['url'][:55]}")

    valid = [r for r in results if r["ok"] and r.get("china_channels", 0) >= args.min_china]
    valid.sort(key=lambda x: x.get("china_channels", 0), reverse=True)

    print(f"\n=== 有效候选(可拉取且中国频道>={args.min_china}): {len(valid)} / {len(lives)} ===")
    for r in valid[:30]:
        print(f"  中={r['china_channels']:>4} 总={r['total_channels']:>5}  {r['name'][:12]:12} {r['url'][:60]}")

    with open(args.report, "w", encoding="utf-8") as f:
        json.dump({"screened_at": datetime.now(timezone.utc).isoformat(),
                   "total": len(lives), "valid": len(valid),
                   "valid_entries": valid, "all": results}, f, ensure_ascii=False, indent=2)
    print(f"\n报告: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
