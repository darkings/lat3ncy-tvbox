#!/usr/bin/env python3
"""Discover and conservatively pre-screen public MacCMS VOD endpoints.

Passing this collector means only that search, keyword matching, detail lookup,
and extraction of HTTP(S) playback candidates worked.  It never claims media
success; HLS segment or ffprobe verification remains a mandatory later stage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ponyo_source_manager.core import net
from ponyo_source_manager.core.common import DATA_DIR, REPORT_DIR
from ponyo_source_manager.discovery.discover_sources import check_url_safety

# 扩展关键词矩阵：覆盖影视/动画/儿童/音乐/短剧/通用词。
# 实测（2026-08-01）原 3 词有 34 个 endpoint 搜索全空，其中 9 个换词即命中；
# 多词矩阵 + 任一命中通过可救回这些源。
DEFAULT_KEYWORDS = (
    "庆余年",
    "流浪地球",
    "熊出没",  # 原有 3 词
    "斗罗大陆",
    "名侦探柯南",  # 动画
    "小猪佩奇",  # 儿童
    "周杰伦",  # 音乐
    "逆袭",
    "闪婚",  # 短剧
    "中国",
    "2024",
    "爱情",  # 通用
)
DEFAULT_ENDPOINTS_PER_RUN = 30
SUPPORTED_PATH_MARKERS = (
    "/api.php/provide/vod",
    "/provide/vod",
    "/cjapi/",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_json(url: str, *, timeout: float = 12.0) -> dict[str, Any]:
    value = json.loads(net.fetch_text(url, timeout=timeout, max_bytes=2_048_576))
    if not isinstance(value, dict):
        raise ValueError("MacCMS response is not a JSON object")
    return value


def normalize_endpoint(url: str) -> str | None:
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    path_lower = parts.path.lower().rstrip("/")
    if not any(marker in path_lower for marker in SUPPORTED_PATH_MARKERS):
        return None
    # Keep endpoint-specific authentication parameters but remove request fields.
    ignored = {"ac", "action", "wd", "ids", "pg", "page", "limit"}
    query = urlencode(
        [(k, v) for k, v in parse_qsl(parts.query) if k.lower() not in ignored]
    )
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path.rstrip("/") + "/", query, "")
    )


def _request_url(endpoint: str, **params: str) -> str:
    parts = urlsplit(endpoint)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.extend(params.items())
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def _vod_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    value = payload.get("list", payload.get("data", []))
    return (
        [item for item in value if isinstance(item, dict)]
        if isinstance(value, list)
        else []
    )


def _keyword_matches(
    items: Iterable[dict[str, Any]], keyword: str
) -> list[dict[str, Any]]:
    folded = keyword.casefold()
    return [
        item for item in items if folded in str(item.get("vod_name", "")).casefold()
    ]


def extract_play_urls(detail: dict[str, Any]) -> list[str]:
    raw = str(detail.get("vod_play_url", ""))
    urls: list[str] = []
    for route in raw.split("$$$"):
        for episode in route.split("#"):
            candidate = episode.rsplit("$", 1)[-1].strip()
            parts = urlsplit(candidate)
            if parts.scheme in ("http", "https") and parts.hostname:
                urls.append(candidate)
    return list(dict.fromkeys(urls))


def load_endpoints_from_db(db_path: str | Path) -> list[str]:
    """Read only likely MacCMS APIs; discovery must not alter source state."""
    with sqlite3.connect(db_path) as con:
        rows = con.execute(
            "SELECT DISTINCT api FROM raw_source WHERE api IS NOT NULL AND api <> ''"
        ).fetchall()
    endpoints: list[str] = []
    seen: set[str] = set()
    for (raw_url,) in rows:
        endpoint = normalize_endpoint(str(raw_url))
        if endpoint and endpoint not in seen:
            seen.add(endpoint)
            endpoints.append(endpoint)
    # Fair rotation: never-probed endpoints first, then the oldest evidence.
    # Structurally-failed endpoints (ssrf/dead links) are pushed to the back
    # so the per-run budget is not consumed by links that can never pass.
    with sqlite3.connect(db_path) as con:
        last_probed = dict(
            con.execute(
                "SELECT endpoint, MAX(probed_at) FROM maccms_probe_result GROUP BY endpoint"
            ).fetchall()
        )
        last_failed = dict(
            con.execute(
                "SELECT endpoint, MAX(probed_at) FROM maccms_probe_result "
                "WHERE failure_stage IN ('ssrf', 'unsupported_endpoint') GROUP BY endpoint"
            ).fetchall()
        )
    endpoints.sort(
        key=lambda endpoint: (
            last_failed.get(endpoint) is not None,
            last_probed.get(endpoint) is not None,
            last_probed.get(endpoint) or "",
        )
    )
    return endpoints


@dataclass(frozen=True)
class KeywordProbe:
    keyword: str
    search_ok: bool
    keyword_hit: bool
    detail_ok: bool
    playable_url_count: int
    failure_stage: str | None
    matched_name: str | None
    content_id: str | None
    sample_urls: tuple[str, ...]


class MacCMSCollector:
    def __init__(
        self,
        db_path: str | Path,
        *,
        fetch_json: Callable[[str], dict[str, Any]] = _fetch_json,
        safety_check: Callable[[str], bool] = check_url_safety,
        now: Callable[[], str] = _now,
    ) -> None:
        self.db_path = Path(db_path)
        self.fetch_json = fetch_json
        self.safety_check = safety_check
        self.now = now

    def _probe_keyword(self, endpoint: str, keyword: str) -> KeywordProbe:
        try:
            search = self.fetch_json(_request_url(endpoint, ac="detail", wd=keyword))
        except Exception:
            return KeywordProbe(
                keyword, False, False, False, 0, "search", None, None, ()
            )
        matches = _keyword_matches(_vod_list(search), keyword)
        if not matches:
            return KeywordProbe(
                keyword, True, False, False, 0, "keyword_miss", None, None, ()
            )
        chosen = matches[0]
        content_id = str(chosen.get("vod_id", "")).strip()
        name = str(chosen.get("vod_name", "")).strip()
        if not content_id:
            return KeywordProbe(
                keyword, True, True, False, 0, "missing_content_id", name, None, ()
            )
        try:
            detail_payload = self.fetch_json(
                _request_url(endpoint, ac="detail", ids=content_id)
            )
        except Exception:
            return KeywordProbe(
                keyword, True, True, False, 0, "detail", name, content_id, ()
            )
        details = _vod_list(detail_payload)
        if not details:
            return KeywordProbe(
                keyword, True, True, False, 0, "detail_empty", name, content_id, ()
            )
        play_urls = extract_play_urls(details[0])
        if not play_urls:
            return KeywordProbe(
                keyword, True, True, True, 0, "no_play_url", name, content_id, ()
            )
        return KeywordProbe(
            keyword,
            True,
            True,
            True,
            len(play_urls),
            None,
            name,
            content_id,
            tuple(play_urls[:3]),
        )

    def _persist(
        self,
        run_id: str,
        endpoint: str,
        probes: list[KeywordProbe],
        passed: bool,
        failure_stage: str | None = None,
    ) -> None:
        timestamp = self.now()
        scope = urlsplit(endpoint).hostname or endpoint
        with sqlite3.connect(self.db_path) as con:
            if not probes:
                # 空 probes（ssrf / unsupported_endpoint）：写一条 header 记录，
                # 让结构性失败的端点不再被当作 never-probed 每轮占用预算。
                con.execute(
                    "INSERT INTO maccms_probe_result "
                    "(run_id, endpoint, keyword, search_ok, keyword_hit, detail_ok, "
                    "playable_url_count, failure_stage, evidence_json, probed_at) "
                    "VALUES (?, ?, '', 0, 0, 0, 0, ?, ?, ?)",
                    (
                        run_id,
                        endpoint,
                        failure_stage or "quick_probe",
                        json.dumps(
                            {"matched_name": None, "media_verified": False},
                            ensure_ascii=False,
                        ),
                        timestamp,
                    ),
                )
            for probe in probes:
                con.execute(
                    "INSERT OR REPLACE INTO maccms_probe_result "
                    "(run_id, endpoint, keyword, search_ok, keyword_hit, detail_ok, "
                    "playable_url_count, failure_stage, evidence_json, probed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        endpoint,
                        probe.keyword,
                        int(probe.search_ok),
                        int(probe.keyword_hit),
                        int(probe.detail_ok),
                        probe.playable_url_count,
                        probe.failure_stage,
                        json.dumps(
                            {
                                "matched_name": probe.matched_name,
                                "content_id": probe.content_id,
                                "sample_urls": probe.sample_urls,
                                "media_verified": False,
                            },
                            ensure_ascii=False,
                        ),
                        timestamp,
                    ),
                )
            if passed:
                digest = hashlib.sha256(endpoint.encode("utf-8")).hexdigest()
                old = con.execute(
                    "SELECT first_seen_at FROM discovered_artifact "
                    "WHERE connector='maccms' AND scope=? AND artifact_url=?",
                    (scope, endpoint),
                ).fetchone()
                first_seen = old[0] if old else timestamp
                con.execute(
                    "INSERT INTO discovered_artifact "
                    "(connector, scope, artifact_url, effective_url, artifact_kind, revision, "
                    "content_sha256, metadata_json, first_seen_at, last_seen_at, last_changed_at) "
                    "VALUES ('maccms', ?, ?, ?, 'maccms_endpoint', NULL, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(connector, scope, artifact_url) DO UPDATE SET "
                    "last_seen_at=excluded.last_seen_at, metadata_json=excluded.metadata_json",
                    (
                        scope,
                        endpoint,
                        endpoint,
                        digest,
                        json.dumps(
                            {"quick_probe_pass": True, "media_verified": False},
                            ensure_ascii=False,
                        ),
                        first_seen,
                        timestamp,
                        timestamp,
                    ),
                )

    def probe_endpoint(
        self,
        url: str,
        *,
        keywords: Iterable[str] = DEFAULT_KEYWORDS,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        endpoint = normalize_endpoint(url)
        result: dict[str, Any] = {
            "input_url": url,
            "endpoint": endpoint,
            "run_id": run_id or uuid.uuid4().hex,
            "passed": False,
            "media_verified": False,
            "failure_stage": None,
            "probes": [],
        }
        if endpoint is None:
            result["failure_stage"] = "unsupported_endpoint"
            self._persist(result["run_id"], url, [], False, "unsupported_endpoint")
            return result
        if not self.safety_check(endpoint):
            result["failure_stage"] = "ssrf"
            self._persist(result["run_id"], endpoint, [], False, "ssrf")
            return result
        keyword_list = [str(value).strip() for value in keywords if str(value).strip()]
        probes = [self._probe_keyword(endpoint, keyword) for keyword in keyword_list]
        # 任一关键词命中且暴露播放候选即通过。原实现要求全部关键词命中，
        # 导致固定 3 词下对部分源（如听书/短剧/音乐）整体误判为搜索失败。
        # 真实媒体验证仍由下游 maccms_media 完成，此处只做候选资格判定。
        passed = bool(probes) and any(
            probe.search_ok
            and probe.keyword_hit
            and probe.detail_ok
            and probe.playable_url_count > 0
            for probe in probes
        )
        result["passed"] = passed
        result["failure_stage"] = (
            None
            if passed
            else next(
                (probe.failure_stage for probe in probes if probe.failure_stage),
                "quick_probe",
            )
        )
        result["probes"] = [probe.__dict__ for probe in probes]
        self._persist(result["run_id"], endpoint, probes, passed)
        return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DATA_DIR / "sources.db"))
    parser.add_argument("--endpoints-file")
    parser.add_argument("--limit", type=int, default=DEFAULT_ENDPOINTS_PER_RUN)
    parser.add_argument(
        "--report", default=str(REPORT_DIR / "maccms-discovery-report.json")
    )
    args = parser.parse_args()
    endpoints = load_endpoints_from_db(args.db)
    if args.endpoints_file:
        # 显式指定的端点必须优先于库内队列，否则会被 [:limit] 截断永远选不到。
        file_endpoints = [
            line.strip()
            for line in Path(args.endpoints_file)
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        file_set = set(file_endpoints)
        endpoints = file_endpoints + [e for e in endpoints if e not in file_set]
    collector = MacCMSCollector(args.db)
    run_id = uuid.uuid4().hex
    limit = max(1, min(args.limit, 300))
    selected = list(dict.fromkeys(endpoints))[:limit]
    results = [
        collector.probe_endpoint(endpoint, run_id=run_id) for endpoint in selected
    ]
    report = {
        "generated_at": _now(),
        "run_id": run_id,
        "connector": "maccms",
        "endpoint_budget": limit,
        "queued": len(dict.fromkeys(endpoints)),
        "results": results,
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
