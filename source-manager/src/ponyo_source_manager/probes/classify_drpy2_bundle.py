#!/usr/bin/env python3
"""Read-only full-chain classification for an immutable drpy2 rule bundle."""

from __future__ import annotations

import argparse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import ProxyHandler, Request, build_opener

from ponyo_source_manager.core.common import assert_no_proxy
from ponyo_source_manager.probes.playback import verify_playback

DIRECT_LINE_HINTS = ("m3u8", "直连", "量子", "非凡", "百度", "火狐", "淘片")


def _media_verified(playback: dict) -> bool:
    return (
        playback.get("m3u8_ok") == 1
        and playback.get("segments_ok", 0) >= 1
    ) or playback.get("ffprobe_valid") == 1


def _request_json(base_url: str, password: str, module: str, params: dict, timeout: int) -> dict:
    query = {"pwd": password, "adpt": "dr", **params}
    url = f"{base_url.rstrip('/')}/api/{quote(module, safe='')}?{urlencode(query)}"
    opener = build_opener(ProxyHandler({}))
    with opener.open(Request(url, headers={"User-Agent": "ponyo-source-manager/1.0"}), timeout=timeout) as response:
        data = json.load(response)
    if not isinstance(data, dict) or data.get("error"):
        raise ValueError(f"invalid runtime response: {data!r}")
    return data


def _episodes(vod: dict) -> list[dict]:
    flags = str(vod.get("vod_play_from") or "").split("$$$")
    groups = str(vod.get("vod_play_url") or "").split("$$$")
    episodes = []
    for index, group in enumerate(groups):
        flag = (flags[index] if index < len(flags) else f"line-{index + 1}").strip()
        first = next((item for item in group.split("#") if item.strip()), "")
        if not first:
            continue
        split_at = first.find("$")
        name = first[:split_at].strip() if split_at >= 0 else "首集"
        play_id = first[split_at + 1:].strip() if split_at >= 0 else first.strip()
        if play_id:
            episodes.append({"flag": flag, "name": name, "play_id": play_id})
    return sorted(
        episodes,
        key=lambda item: 0 if any(hint.lower() in item["flag"].lower() for hint in DIRECT_LINE_HINTS) else 1,
    )


def classify_rule(rule: dict, base_url: str, password: str, keywords: list[str],
                  *, timeout: int = 12, playback_probe=verify_playback) -> dict:
    started = time.monotonic()
    result = {
        "module": rule["module"], "url": rule["url"], "source_ids": rule.get("source_ids", []),
        "names": rule.get("names", []), "stage": "init", "success": False,
    }
    try:
        selected = None
        search_observations = []
        for keyword in keywords:
            data = _request_json(base_url, password, rule["module"], {"wd": keyword, "pg": 1}, timeout)
            items = data.get("list") if isinstance(data.get("list"), list) else []
            hits = [item for item in items if keyword in str(item.get("vod_name") or item.get("name") or "")]
            search_observations.append({"keyword": keyword, "count": len(items), "hits": len(hits)})
            if hits:
                selected = (keyword, hits[0])
                break
        result["search"] = search_observations
        if not selected:
            result["stage"] = "search"
            result["error"] = "no keyword-relevant search result"
            return result
        keyword, item = selected
        item_id = str(item.get("vod_id") or item.get("id") or "").strip()
        if not item_id:
            raise ValueError("search hit missing vod_id")
        result["selected"] = {"keyword": keyword, "vod_id": item_id,
                              "vod_name": item.get("vod_name") or item.get("name")}

        detail_data = _request_json(base_url, password, rule["module"], {"ac": "detail", "ids": item_id}, timeout)
        detail_list = detail_data.get("list") if isinstance(detail_data.get("list"), list) else []
        if not detail_list or not isinstance(detail_list[0], dict):
            result["stage"] = "detail"
            result["error"] = "empty detail"
            return result
        vod = detail_list[0]
        result["detail"] = {"vod_name": vod.get("vod_name"), "vod_play_from": vod.get("vod_play_from")}
        episodes = _episodes(vod)
        result["episode_count"] = len(episodes)
        if not episodes:
            result["stage"] = "episode"
            result["error"] = "detail returned no episodes"
            return result

        attempts = []
        for episode in episodes[:4]:
            try:
                play = _request_json(base_url, password, rule["module"],
                                     {"play": episode["play_id"], "flag": episode["flag"]}, timeout)
                play_url = str(play.get("url") or play.get("play_url") or "").strip()
                if not play_url.startswith(("http://", "https://")):
                    raise ValueError("play URL is not absolute HTTP(S)")
                headers = play.get("header") or play.get("headers") or {}
                playback = playback_probe(play_url, mode="fast", ext_str=json.dumps({"header": headers}, ensure_ascii=False))
                attempt = {"flag": episode["flag"], "name": episode["name"], "url": play_url,
                           "playback": playback}
                attempts.append(attempt)
                if _media_verified(playback):
                    result["stage"] = "complete"
                    result["success"] = True
                    result["selected_play"] = attempt
                    return result
            except Exception as error:  # one bad line must not hide another direct line
                attempts.append({"flag": episode["flag"], "name": episode["name"],
                                 "error": f"{type(error).__name__}: {error}"})
        result["stage"] = "playback"
        result["play_attempts"] = attempts
        result["error"] = "no tested line passed real media verification"
        return result
    except Exception as error:
        result["stage"] = result.get("stage") or "runtime"
        result["error"] = f"{type(error).__name__}: {error}"
        return result
    finally:
        result["latency_ms"] = int((time.monotonic() - started) * 1000)


def classify_bundle(manifest_path: str, base_urls: list[str], password: str, output_path: str,
                    *, keywords: list[str], timeout: int = 12) -> dict:
    if assert_no_proxy():
        raise SystemExit("代理环境变量非空，drpy2运行时分类中止（需无代理）。")
    rules = json.loads(Path(manifest_path).read_text(encoding="utf-8")).get("rules", [])
    if not rules or not base_urls:
        raise ValueError("manifest rules and base URLs must be non-empty")
    shards = [rules[index::len(base_urls)] for index in range(len(base_urls))]
    progress = {"done": 0}
    lock = threading.Lock()

    def worker(worker_index: int) -> list[dict]:
        results = []
        for rule in shards[worker_index]:
            result = classify_rule(rule, base_urls[worker_index], password, keywords, timeout=timeout)
            results.append(result)
            with lock:
                progress["done"] += 1
                if progress["done"] % 10 == 0 or progress["done"] == len(rules):
                    print(json.dumps({"progress": progress["done"], "total": len(rules),
                                      "passed": result["success"], "module": rule["module"]}, ensure_ascii=False), flush=True)
        return results

    with ThreadPoolExecutor(max_workers=len(base_urls)) as executor:
        nested = list(executor.map(worker, range(len(base_urls))))
    results = [result for shard in nested for result in shard]
    results.sort(key=lambda item: item["module"])
    stage_counts: dict[str, int] = {}
    for result in results:
        stage_counts[result["stage"]] = stage_counts.get(result["stage"], 0) + 1
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "summary": {"total": len(results), "passed": sum(item["success"] for item in results),
                    "failed": sum(not item["success"] for item in results), "stage_counts": stage_counts},
        "results": results,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="只读分类 drpy2 规则包")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--base-url", action="append", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--keywords", default="熊出没,庆余年,流浪地球")
    parser.add_argument("--timeout", type=int, default=12)
    args = parser.parse_args()
    report = classify_bundle(args.manifest, args.base_url, args.password, args.output,
                             keywords=[item.strip() for item in args.keywords.split(",") if item.strip()],
                             timeout=args.timeout)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
