#!/usr/bin/env python3
"""从点播源的上游 TVBox 配置中提取 lives 直播入口。

思路：点播源的 origin 字段是完整 TVBox 配置 URL，这些配置几乎都含
lives[] 直播块。提取 lives[].url（解析相对路径为绝对地址），去重后
即为候选直播源——实现"点播源伴随直播源"的挖掘。

对 GitHub raw 域名做 CDN 回退（国内服务器直连 raw 常被墙/超时）。
默认只提取+打印+写报告，不做测速、不写候选池。
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from ponyo_source_manager.core.common import DATA_DIR, REPORT_DIR
from ponyo_source_manager.core import net


def github_mirror_urls(url: str) -> list[str]:
    """为 GitHub raw URL 生成 CDN 镜像回退列表。非 GitHub URL 原样返回。"""
    m = re.match(r"https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/(.+)", url)
    if m:
        repo_owner, repo_name, rest = m.group(1), m.group(2), m.group(3)
        # rest = branch/path...  ->  jsDelivr 需要 branch@path
        parts = rest.split("/", 1)
        if len(parts) == 2:
            branch, path = parts
            return [
                url,  # 原始 raw
                f"https://cdn.jsdelivr.net/gh/{repo_owner}/{repo_name}@{branch}/{path}",
                f"https://fastly.jsdelivr.net/gh/{repo_owner}/{repo_name}@{branch}/{path}",
                f"https://gcore.jsdelivr.net/gh/{repo_owner}/{repo_name}@{branch}/{path}",
                f"https://raw.gitmirror.com/{repo_owner}/{repo_name}/{branch}/{path}",
            ]
    return [url]


def fetch_with_fallback(url: str, timeout: int) -> str | None:
    """依次尝试镜像 URL，返回第一个成功的内容。"""
    for u in github_mirror_urls(url):
        try:
            content = net.fetch_text(u, timeout=timeout, limiter=None)
            if content and len(content) > 50:
                return content
        except Exception:
            continue
    return None


def load_top_origins(db_path: str, limit: int) -> list[tuple[str, int]]:
    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT origin, COUNT(*) c FROM raw_source "
        "WHERE origin LIKE 'http%' "
        "GROUP BY origin ORDER BY c DESC LIMIT ?",
        (limit,),
    ).fetchall()
    con.close()
    return [(r[0], r[1]) for r in rows]


def extract_lives(content: str, base_url: str) -> list[dict]:
    try:
        data = json.loads(content)
    except Exception:
        return []
    out = []
    for item in data.get("lives", []) or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()
        if not url:
            continue
        abs_url = urljoin(base_url, url)
        if not abs_url.startswith(("http://", "https://")):
            continue
        out.append({
            "name": str(item.get("name", "")).strip() or "未命名",
            "url": abs_url,
            "type": item.get("type"),
            "epg": item.get("epg"),
            "origin": base_url,
        })
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="从点播源配置提取 lives 直播源")
    p.add_argument("--db", default=str(DATA_DIR / "sources.db"))
    p.add_argument("--top", type=int, default=30)
    p.add_argument("--report", default=str(REPORT_DIR / "lives-from-vod.json"))
    p.add_argument("--timeout", type=int, default=12)
    args = p.parse_args()

    origins = load_top_origins(args.db, args.top)
    print(f"=== 从点播源提取 lives ===")
    print(f"上游配置数: {len(origins)}\n")

    all_lives: list[dict] = []
    seen_urls: set[str] = set()
    ok_origins = 0

    for origin, vod_count in origins:
        print(f"[{vod_count:>4} 源] {origin[:75]}")
        content = fetch_with_fallback(origin, args.timeout)
        if not content:
            print(f"         全部镜像拉取失败")
            continue
        ok_origins += 1
        lives = extract_lives(content, origin)
        new = 0
        for lv in lives:
            if lv["url"] not in seen_urls:
                seen_urls.add(lv["url"])
                all_lives.append(lv)
                new += 1
        print(f"         lives={len(lives)}, 新增去重={new}")

    print(f"\n=== 成功拉取 {ok_origins}/{len(origins)} 个配置, 提取去重直播入口 {len(all_lives)} 个 ===")
    from collections import Counter
    hosts = Counter(urlparse(l["url"]).netloc for l in all_lives)
    for host, cnt in hosts.most_common(25):
        print(f"  {host}: {cnt}")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump({
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "origins_scanned": len(origins),
            "origins_ok": ok_origins,
            "unique_lives": len(all_lives),
            "lives": all_lives,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n报告: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
