#!/usr/bin/env python3
"""Classify playback handoff failures using redacted, non-secret evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

PLATFORM_HOSTS = {
    "v.qq.com", "www.iqiyi.com", "iqiyi.com", "www.youku.com", "youku.com",
    "www.bilibili.com", "bilibili.com", "tv.cctv.com", "www.mgtv.com",
}
MEDIA_SUFFIXES = (".mp4", ".mkv", ".ts", ".flv", ".webm", ".mp3", ".aac", ".m4a")
HLS_SUFFIXES = (".m3u8", ".m3u")
PAGE_SUFFIXES = (".html", ".htm", ".shtml", ".php", ".asp", ".aspx")
SENSITIVE_HEADER_RE = re.compile(r"(?i)authorization|cookie|token|secret|password|key")


def classify_play_url(play_url: str) -> dict:
    """Return only redacted URL metadata; never retain path, query, or fragment."""
    value = str(play_url or "").strip()
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""
    try:
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower()
        path = parsed.path.lower()
    except ValueError:
        return {
            "url_class": "invalid_url", "scheme": "", "host": "",
            "suffix": "", "url_sha256": digest,
        }
    suffix = Path(path).suffix[:16]
    if not value or scheme not in {"http", "https"} or not host:
        url_class = "invalid_url"
    elif host in {"127.0.0.1", "localhost"}:
        url_class = "local_proxy"
    elif host in PLATFORM_HOSTS or path.endswith(PAGE_SUFFIXES):
        url_class = "platform_or_web_page"
    elif path.endswith(HLS_SUFFIXES) or "m3u8" in value.lower():
        url_class = "hls"
    elif path.endswith(MEDIA_SUFFIXES):
        url_class = "direct_media"
    elif any(marker in path for marker in ("/parse", "/parser", "/jx/", "/api/")):
        url_class = "parser_endpoint"
    else:
        url_class = "unknown_url"
    return {
        "url_class": url_class,
        "scheme": scheme,
        "host": host,
        "suffix": suffix,
        "url_sha256": digest,
    }


def sanitize_playurl_evidence(result: dict) -> dict:
    evidence = classify_play_url(str(result.get("play_url") or ""))
    headers = result.get("header", result.get("headers", {}))
    if not isinstance(headers, dict):
        headers = {}
    header_keys = sorted({str(key).strip().lower() for key in headers if str(key).strip()})
    evidence.update({
        "requires_headers": bool(header_keys),
        "header_keys": header_keys,
        "sensitive_header_present": any(SENSITIVE_HEADER_RE.search(key) for key in header_keys),
    })
    return evidence


def _result_for(results: list[dict], test_type: str) -> dict | None:
    return next((item for item in results if item.get("test_type") == test_type), None)


def _outcome(result: dict | None, missing: str) -> str:
    if not result:
        return missing
    if result.get("success") in (1, True):
        return "success"
    return str(result.get("failure_stage") or "failed_unclassified")


def build_playback_audit(report: dict, *, cohort_limit: int = 50) -> dict:
    classifications: Counter[str] = Counter()
    transitions: Counter[str] = Counter()
    rows = []
    for source in report.get("sources", []):
        results = source.get("results", []) if isinstance(source.get("results"), list) else []
        playurl = _result_for(results, "playurl")
        if not playurl or not playurl.get("play_url"):
            continue
        redacted = sanitize_playurl_evidence(playurl)
        playback = _result_for(results, "playback")
        ffprobe = _result_for(results, "ffprobe")
        playback_outcome = _outcome(playback, "playback_missing")
        ffprobe_outcome = _outcome(ffprobe, "ffprobe_missing")
        classification = redacted["url_class"]
        classifications[classification] += 1
        transitions[f"{classification}->{playback_outcome}"] += 1
        transitions[f"{classification}->{ffprobe_outcome}"] += 1
        rows.append({
            "fingerprint": str(source.get("fingerprint") or ""),
            "name": str(source.get("name") or ""),
            "content_lane": str(source.get("content_lane") or ""),
            **redacted,
            "playurl_success": bool(playurl.get("success")),
            "playback_outcome": playback_outcome,
            "ffprobe_outcome": ffprobe_outcome,
        })
    priority = {
        "platform_or_web_page": 0,
        "unknown_url": 1,
        "parser_endpoint": 2,
        "local_proxy": 3,
        "hls": 4,
        "direct_media": 5,
        "invalid_url": 6,
    }
    candidates = sorted(
        (row for row in rows if row["playback_outcome"] != "success" or row["ffprobe_outcome"] != "success"),
        key=lambda row: (
            priority.get(row["url_class"], 99),
            row["playback_outcome"] == "success",
            row["fingerprint"],
        ),
    )[:max(0, cohort_limit)]
    return {
        "summary": {
            "sources_in_report": len(report.get("sources", [])),
            "play_urls_classified": len(rows),
            "classifications": dict(sorted(classifications.items())),
            "transitions": dict(sorted(transitions.items())),
            "remediation_candidates": len(candidates),
        },
        "candidates": candidates,
        "evidence": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="生成脱敏播放地址失败类型审计")
    parser.add_argument("--input", required=True, help="drpy-test-report.json")
    parser.add_argument("--output", required=True)
    parser.add_argument("--cohort-limit", type=int, default=50)
    args = parser.parse_args()
    source = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = build_playback_audit(source, cohort_limit=args.cohort_limit)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
