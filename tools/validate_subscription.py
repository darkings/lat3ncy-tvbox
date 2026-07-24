#!/usr/bin/env python3
"""Probe TVBox subscription dependencies without using a network proxy."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


URL_RE = re.compile(r"https?://[^\s\"<>]+")


def collect_urls(value):
    found = []
    if isinstance(value, str):
        found.extend(URL_RE.findall(value))
    elif isinstance(value, dict):
        for child in value.values():
            found.extend(collect_urls(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(collect_urls(child))
    return [url.rstrip("),]}") for url in found]


def probe_target(url, accelerator):
    if "raw.githubusercontent.com/" in url:
        if "jsdelivr.net" in accelerator:
            parsed = urlsplit(url)
            parts = parsed.path.strip("/").split("/", 3)
            if len(parts) == 4:
                owner, repo, ref, asset = parts
                return f"{accelerator.rstrip('/')}/gh/{owner}/{repo}@{ref}/{asset}"
        return accelerator.rstrip("/") + "/" + url
    if "{" in url or "}" in url:
        parsed = urlsplit(url)
        return urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))
    return url


def probe(url, accelerator, timeout, rounds):
    target = probe_target(url, accelerator)
    attempts = []
    for _ in range(rounds):
        started = time.monotonic()
        command = [
            "curl", "--noproxy", "*", "-L", "-sS",
            "--connect-timeout", str(min(timeout, 8)),
            "--max-time", str(timeout), "--range", "0-65535",
            "-o", "/dev/null", "-w", "%{http_code}\t%{size_download}\t%{content_type}",
            target,
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        parts = result.stdout.strip().split("\t", 2)
        status = int(parts[0]) if parts and parts[0].isdigit() else 0
        size = int(float(parts[1])) if len(parts) > 1 and parts[1] else 0
        content_type = parts[2] if len(parts) > 2 else ""
        attempts.append({
            "status": status,
            "bytes": size,
            "content_type": content_type,
            "seconds": round(time.monotonic() - started, 3),
            "error": result.stderr.strip(),
        })
    successes = sum(1 for item in attempts if 200 <= item["status"] < 300 and item["bytes"] > 0)
    return {
        "url": url,
        "target": target,
        "ok": successes == rounds,
        "successes": successes,
        "rounds": rounds,
        "attempts": attempts,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("--accelerator", default="https://ghproxy.net")
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=12)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    sites = config.get("sites", [])
    site_urls = []
    all_urls = set()
    for index, site in enumerate(sites):
        urls = []
        for field in ("api", "ext"):
            urls.extend(collect_urls(site.get(field)))
        urls = sorted({url for url in urls if "127.0.0.1" not in url and "localhost" not in url})
        site_urls.append((index, site, urls))
        all_urls.update(urls)

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(probe, url, args.accelerator, args.timeout, args.rounds): url
            for url in sorted(all_urls)
        }
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results[result["url"]] = result

    site_results = []
    for index, site, urls in site_urls:
        checks = [results[url] for url in urls]
        if not checks:
            verdict = "builtin-or-conditional"
        elif all(check["ok"] for check in checks):
            verdict = "verified"
        elif any(check["successes"] > 0 for check in checks):
            verdict = "partial"
        else:
            verdict = "unreachable"
        site_results.append({
            "index": index,
            "key": site.get("key", ""),
            "name": site.get("name", ""),
            "verdict": verdict,
            "urls": urls,
        })

    summary = {}
    for site in site_results:
        summary[site["verdict"]] = summary.get(site["verdict"], 0) + 1
    report = {
        "config": str(args.config),
        "accelerator": args.accelerator,
        "proxy_disabled": True,
        "rounds": args.rounds,
        "summary": summary,
        "sites": site_results,
        "url_results": [results[url] for url in sorted(results)],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
