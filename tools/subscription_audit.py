#!/usr/bin/env python3
"""Audit and merge TVBox subscriptions into a self-contained config."""

from __future__ import annotations

import argparse
import csv
import json
import re
import ssl
import socket
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen


SOURCES = {
    "jsm": "https://raw.githubusercontent.com/qist/tvbox/master/jsm.json",
    "fty": "https://raw.githubusercontent.com/qist/tvbox/master/fty.json",
}
URL_RE = re.compile(r"^https?://", re.I)
URL_FIND_RE = re.compile(r"https?://[^,\s\"']+", re.I)
ASSET_EXTENSIONS = (".json", ".js", ".py", ".txt", ".jar", ".m3u", ".m3u8")


def resolve_string(value: str, base: str) -> str:
    if not value.startswith(("./", "../")):
        return value
    if ";md5;" in value:
        path, digest = value.split(";md5;", 1)
        return f"{urljoin(base, path)};md5;{digest}"
    return urljoin(base, value)


def resolve_relative(value: Any, base: str) -> Any:
    if isinstance(value, dict):
        return {key: resolve_relative(item, base) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_relative(item, base) for item in value]
    if isinstance(value, str):
        return resolve_string(value, base)
    return value


def strip_md5(value: str) -> str:
    return value.split(";md5;", 1)[0]


def iri_to_uri(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname.encode("idna").decode("ascii") if parts.hostname else ""
    if parts.port:
        host = f"{host}:{parts.port}"
    if parts.username:
        auth = quote(parts.username, safe="")
        if parts.password:
            auth += ":" + quote(parts.password, safe="")
        host = f"{auth}@{host}"
    return urlunsplit(
        (parts.scheme, host, quote(parts.path, safe="/%:@+~!$&'()*;,=-._"),
         quote(parts.query, safe="=&?/:@+~!$'()*;,%-._{}"), "")
    )


def collect_urls(value: Any, location: str = "root", out: dict[str, set[str]] | None = None) -> dict[str, set[str]]:
    if out is None:
        out = defaultdict(set)
    if isinstance(value, dict):
        for key, item in value.items():
            collect_urls(item, f"{location}.{key}", out)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            collect_urls(item, f"{location}[{index}]", out)
    elif isinstance(value, str):
        candidates = URL_FIND_RE.findall(strip_md5(value.strip()))
        for candidate in candidates:
            out[candidate].add(location)
    return out


def check_url(url: str, timeout: float) -> dict[str, Any]:
    if any(marker in url for marker in ("{name}", "{date}", "{cate", "{area}", "{year}", "{wd}")):
        return {"state": "template", "status": None, "final_url": url, "error": "contains runtime placeholders"}
    try:
        uri = iri_to_uri(url)
    except (UnicodeError, ValueError) as exc:
        return {"state": "failed", "status": None, "final_url": url, "error": f"invalid URL: {exc}"}
    parts = urlsplit(uri)
    if parts.hostname in ("127.0.0.1", "localhost", "0.0.0.0"):
        return {"state": "local", "status": None, "final_url": url, "error": "device-local runtime URL"}
    if "dns-query" in parts.path:
        return {"state": "contextual", "status": None, "final_url": url, "error": "requires a DNS-over-HTTPS request payload"}
    if re.search(r"(?:[?&](?:url|v)=)$", url, re.I):
        return {"state": "contextual", "status": None, "final_url": url, "error": "requires a media URL parameter"}
    request = Request(
        uri,
        headers={
            "User-Agent": "Mozilla/5.0 (Android 13; TV) PonyoTV-Audit/1.0",
            "Accept": "*/*",
            "Range": "bytes=0-1023",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
            response.read(1024)
            status = response.getcode() or 200
            state = "active" if 200 <= status < 400 else "failed"
            return {"state": state, "status": status, "final_url": response.geturl(), "error": ""}
    except HTTPError as exc:
        state = "restricted" if exc.code in (401, 403, 405, 429) else "failed"
        return {"state": state, "status": exc.code, "final_url": exc.geturl(), "error": str(exc.reason)}
    except (URLError, TimeoutError, socket.timeout, ssl.SSLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        return {"state": "failed", "status": None, "final_url": url, "error": str(reason)}


def normalized_key(item: dict[str, Any]) -> str:
    return str(item.get("key") or item.get("name") or item.get("url") or "").strip().lower()


def merge_unique(first: list[Any], second: list[Any]) -> tuple[list[Any], int]:
    result = deepcopy(first)
    seen: set[str] = set()
    for item in result:
        if isinstance(item, dict):
            seen.add(normalized_key(item))
        else:
            seen.add(json.dumps(item, sort_keys=True, ensure_ascii=False))
    skipped = 0
    for item in second:
        key = normalized_key(item) if isinstance(item, dict) else json.dumps(item, sort_keys=True, ensure_ascii=False)
        if key and key in seen:
            skipped += 1
            continue
        result.append(deepcopy(item))
        seen.add(key)
    return result, skipped


def is_critical_asset(url: str) -> bool:
    path = urlsplit(strip_md5(url)).path.lower()
    return path.endswith(ASSET_EXTENSIONS) or "raw.githubusercontent.com" in url


def item_required_urls(item: dict[str, Any]) -> list[str]:
    required: list[str] = []
    for field in ("api", "jar"):
        value = item.get(field)
        if isinstance(value, str) and URL_RE.match(strip_md5(value)):
            required.append(strip_md5(value))
    for url in collect_urls(item.get("ext"), "ext"):
        if is_critical_asset(url):
            required.append(url)
    return sorted(set(required))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--workers", type=int, default=24)
    args = parser.parse_args()

    subscription = args.project / "subscription"
    source_dir = subscription / "source"
    report_dir = subscription / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    configs: dict[str, dict[str, Any]] = {}
    for name, source_url in SOURCES.items():
        raw = json.loads((source_dir / f"{name}.json").read_text(encoding="utf-8"))
        configs[name] = resolve_relative(raw, source_url)

    jsm = configs["jsm"]
    fty = configs["fty"]
    fty_jar = str(fty.get("spider", ""))
    fty_sites = deepcopy(fty.get("sites", []))
    for site in fty_sites:
        if isinstance(site, dict) and site.get("type") == 3 and not site.get("jar") and fty_jar:
            site["jar"] = fty_jar

    merged = deepcopy(jsm)
    merged["sites"], duplicate_sites = merge_unique(jsm.get("sites", []), fty_sites)
    merged["lives"], duplicate_lives = merge_unique(jsm.get("lives", []), fty.get("lives", []))
    merged["parses"], duplicate_parses = merge_unique(jsm.get("parses", []), fty.get("parses", []))
    merged["rules"], duplicate_rules = merge_unique(jsm.get("rules", []), fty.get("rules", []))

    url_locations = collect_urls(merged)
    checks: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(check_url, url, args.timeout): url for url in url_locations}
        for future in as_completed(futures):
            url = futures[future]
            checks[url] = future.result()

    dropped_sites: list[dict[str, Any]] = []
    verified_sites: list[dict[str, Any]] = []
    for site in merged.get("sites", []):
        required = item_required_urls(site)
        hard_failures = [url for url in required if checks.get(url, {}).get("state") == "failed"]
        if hard_failures:
            dropped_sites.append({
                "key": site.get("key", ""),
                "name": site.get("name", ""),
                "failed_required_urls": hard_failures,
            })
        else:
            verified_sites.append(site)
    merged["sites"] = verified_sites

    rows = []
    for url in sorted(checks):
        result = checks[url]
        rows.append({
            "state": result["state"],
            "status": result["status"] if result["status"] is not None else "",
            "url": url,
            "final_url": result["final_url"],
            "locations": " | ".join(sorted(url_locations[url])),
            "error": result["error"],
        })

    (subscription / "ponyo.json").write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (report_dir / "url-audit.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=("state", "status", "url", "final_url", "locations", "error"))
        writer.writeheader()
        writer.writerows(rows)

    states = Counter(row["state"] for row in rows)
    audit = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": SOURCES,
        "counts": {
            "source_jsm_sites": len(jsm.get("sites", [])),
            "source_fty_sites": len(fty.get("sites", [])),
            "merged_sites_before_filter": len(verified_sites) + len(dropped_sites),
            "merged_sites_after_filter": len(verified_sites),
            "dropped_sites": len(dropped_sites),
            "lives": len(merged.get("lives", [])),
            "parses": len(merged.get("parses", [])),
            "rules": len(merged.get("rules", [])),
            "unique_urls": len(rows),
            "url_states": dict(states),
            "duplicates_skipped": {
                "sites": duplicate_sites,
                "lives": duplicate_lives,
                "parses": duplicate_parses,
                "rules": duplicate_rules,
            },
        },
        "dropped_sites": dropped_sites,
        "url_results": rows,
        "limitations": [
            "Reachability does not prove that search, parsing, login, or playback succeeds.",
            "Runtime template URLs are recorded but not requested.",
            "HTTP 401/403/405/429 is classified as restricted rather than dead.",
        ],
    }
    (report_dir / "audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    summary = f"""# Ponyo TV 订阅审计

- 生成时间：{audit['generated_at']}
- 合并前站点：jsm {len(jsm.get('sites', []))} + fty {len(fty.get('sites', []))}
- 去重、依赖过滤后站点：{len(verified_sites)}
- 删除关键依赖失效站点：{len(dropped_sites)}
- 直播配置：{len(merged.get('lives', []))}
- 解析配置：{len(merged.get('parses', []))}
- 唯一 URL：{len(rows)}
- URL 状态：{dict(states)}

说明：网络可访问不等于内容可播放；播放仍可能受令牌、地区、登录、接口协议和上游临时故障影响。
"""
    (report_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(json.dumps(audit["counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
