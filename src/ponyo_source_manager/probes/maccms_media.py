#!/usr/bin/env python3
"""Bridge MacCMS quick-probe evidence into real media and ffprobe gates.

The MacCMS collector proves only search/detail/play-URL extraction.  This module
selects those candidates fairly, verifies actual media bytes/segments, runs
ffprobe, and writes the same hard-gate evidence consumed by the scorer.  It
never changes ``list_state``.
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
from typing import Any, Callable
from urllib.parse import urlsplit

from ponyo_source_manager.core.common import DATA_DIR, REPORT_DIR
from ponyo_source_manager.discovery.discover_sources import check_url_safety
from ponyo_source_manager.discovery.maccms_collector import (
    DEFAULT_KEYWORDS,
    normalize_endpoint,
)
from ponyo_source_manager.probes import media_quality, playback


DEFAULT_LIMIT = 10
ADAPTER_VERSION = "maccms-media-v1"
KEYWORD_CONTENT_TYPES = {
    "熊出没": "children",
    "庆余年": "series",
    "流浪地球": "movie",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_hls(url: str) -> bool:
    value = urlsplit(url).path.lower()
    return value.endswith((".m3u8", ".m3u")) or "m3u8" in url.lower()


def _safe_json(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


@dataclass(frozen=True)
class MediaCandidate:
    probe_id: int
    raw_id: int
    fingerprint: str
    endpoint: str
    keyword: str
    title: str
    ext: str
    content_type: str
    sample_urls: tuple[str, ...]
    search_ok: bool
    keyword_hit: bool
    detail_ok: bool
    playable_url_count: int
    quick_failure_stage: str | None
    last_media_probe_at: str | None


def load_candidates(db_path: str | Path) -> list[MediaCandidate]:
    """Return one latest/best MacCMS probe per non-denied fingerprint."""
    with sqlite3.connect(db_path) as con:
        source_rows = con.execute(
            "SELECT r.id,r.api,COALESCE(r.ext,''),n.fingerprint,"
            "COALESCE(ls.state,'candidate') "
            "FROM raw_source r JOIN norm_source n ON n.raw_id=r.id "
            "LEFT JOIN list_state ls ON ls.fingerprint=n.fingerprint "
            "WHERE COALESCE(ls.state,'candidate')<>'deny'"
        ).fetchall()
        probe_rows = con.execute(
            "SELECT id,endpoint,keyword,search_ok,keyword_hit,detail_ok,"
            "playable_url_count,failure_stage,evidence_json,probed_at "
            "FROM maccms_probe_result ORDER BY probed_at DESC,id DESC"
        ).fetchall()
        last_media = dict(con.execute(
            "SELECT fingerprint,MAX(attempted_at) FROM ("
            "SELECT fingerprint,probed_at AS attempted_at FROM media_probe "
            "UNION ALL "
            "SELECT fingerprint,tested_at AS attempted_at FROM drpy_test_result "
            "WHERE adapter_version=?"
            ") GROUP BY fingerprint",
            (ADAPTER_VERSION,),
        ).fetchall())

    endpoints: dict[str, list[tuple[int, str, str]]] = {}
    for raw_id, api, ext, fingerprint, _state in source_rows:
        endpoint = normalize_endpoint(str(api or ""))
        if endpoint:
            endpoints.setdefault(endpoint, []).append(
                (int(raw_id), str(fingerprint), str(ext or ""))
            )

    latest: dict[tuple[str, str], tuple[Any, ...]] = {}
    for row in probe_rows:
        key = (str(row[1]), str(row[2]))
        latest.setdefault(key, row)

    keyword_order = {value: index for index, value in enumerate(DEFAULT_KEYWORDS)}
    by_fingerprint: dict[str, list[MediaCandidate]] = {}
    for (endpoint, keyword), row in latest.items():
        evidence = _safe_json(row[8])
        urls = tuple(
            str(url).strip()
            for url in evidence.get("sample_urls", [])
            if isinstance(url, str) and str(url).strip()
        )[:3]
        for raw_id, fingerprint, ext in endpoints.get(endpoint, []):
            candidate = MediaCandidate(
                probe_id=int(row[0]),
                raw_id=raw_id,
                fingerprint=fingerprint,
                endpoint=endpoint,
                keyword=keyword,
                title=str(evidence.get("matched_name") or keyword),
                ext=ext,
                content_type=KEYWORD_CONTENT_TYPES.get(keyword, "unknown"),
                sample_urls=urls,
                search_ok=bool(row[3]),
                keyword_hit=bool(row[4]),
                detail_ok=bool(row[5]),
                playable_url_count=int(row[6] or 0),
                quick_failure_stage=str(row[7]) if row[7] else None,
                last_media_probe_at=last_media.get(fingerprint),
            )
            by_fingerprint.setdefault(fingerprint, []).append(candidate)

    selected: list[MediaCandidate] = []
    for candidates in by_fingerprint.values():
        candidates.sort(key=lambda item: (
            not bool(
                item.search_ok and item.keyword_hit and item.detail_ok
                and item.playable_url_count > 0 and item.sample_urls
            ),
            keyword_order.get(item.keyword, len(keyword_order)),
            item.probe_id,
        ))
        selected.append(candidates[0])
    selected.sort(key=lambda item: (
        item.last_media_probe_at is not None,
        item.last_media_probe_at or "",
        item.raw_id,
    ))
    return selected


class MacCMSMediaBridge:
    def __init__(
        self,
        db_path: str | Path,
        *,
        playback_check: Callable[..., dict[str, Any]] = playback.verify_playback,
        ffprobe_runner: Callable[..., dict[str, Any]] = media_quality.run_ffprobe,
        safety_check: Callable[[str], bool] = check_url_safety,
        now: Callable[[], str] = _now,
    ) -> None:
        self.db_path = Path(db_path)
        self.playback_check = playback_check
        self.ffprobe_runner = ffprobe_runner
        self.safety_check = safety_check
        self.now = now

    def _save_test_rows(
        self,
        candidate: MediaCandidate,
        run_id: str,
        playback_result: dict[str, Any] | None,
        quality_result: dict[str, Any] | None,
        failure_stage: str | None,
    ) -> None:
        timestamp = self.now()
        functional = (
            ("search", candidate.search_ok and candidate.keyword_hit),
            ("detail", candidate.detail_ok),
            ("episode", candidate.playable_url_count > 0 and bool(candidate.sample_urls)),
        )
        rows: list[tuple[Any, ...]] = []
        for test_type, success in functional:
            rows.append((
                candidate.fingerprint, test_type, candidate.keyword, int(success),
                1 if success else 0, None,
                None if success else candidate.quick_failure_stage or f"{test_type}_failed",
                None if success else candidate.quick_failure_stage or f"{test_type}_failed",
                run_id, ADAPTER_VERSION,
                json.dumps({
                    "connector": "maccms_media",
                    "endpoint": candidate.endpoint,
                    "probe_id": candidate.probe_id,
                }, ensure_ascii=False, sort_keys=True),
                timestamp,
            ))
        if playback_result is not None:
            playback_ok = bool(playback_result.get("success"))
            rows.append((
                candidate.fingerprint, "playback", candidate.keyword,
                int(playback_ok), None, playback_result.get("latency_ms"),
                None if playback_ok else playback_result.get("error") or failure_stage,
                None if playback_ok else failure_stage,
                run_id, ADAPTER_VERSION,
                json.dumps(playback_result, ensure_ascii=False, sort_keys=True),
                timestamp,
            ))
        if quality_result is not None:
            quality_ok = bool(quality_result.get("success"))
            rows.append((
                candidate.fingerprint, "ffprobe", candidate.keyword,
                int(quality_ok), None, None, quality_result.get("error"),
                None if quality_ok else (
                    "duration_gate_failed"
                    if quality_result.get("ffprobe_success")
                    else "ffprobe_failed"
                ),
                run_id, ADAPTER_VERSION,
                json.dumps(quality_result, ensure_ascii=False, sort_keys=True),
                timestamp,
            ))
        with sqlite3.connect(self.db_path) as con:
            con.executemany(
                "INSERT INTO drpy_test_result"
                "(fingerprint,test_type,keyword,success,result_count,latency_ms,error,"
                "failure_stage,run_id,adapter_version,evidence_json,tested_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )

    def _save_media_probe(
        self,
        candidate: MediaCandidate,
        play_url: str,
        quality: dict[str, Any],
    ) -> None:
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT INTO media_probe"
                "(fingerprint,content_title,play_url,width,height,video_codec,"
                "video_bitrate,audio_codec,frame_rate,duration_s,quality_tier,"
                "success,error,probed_at,content_type,min_duration_s,duration_pass,"
                "duration_reason,ffprobe_success) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    candidate.fingerprint, candidate.title, play_url,
                    quality.get("width"), quality.get("height"),
                    quality.get("video_codec"), quality.get("video_bitrate"),
                    quality.get("audio_codec"), quality.get("frame_rate"),
                    quality.get("duration_s"), quality.get("quality_tier"),
                    int(bool(quality.get("success"))), quality.get("error"), self.now(),
                    quality["content_type"], quality["min_duration_s"],
                    quality["duration_pass"], quality["duration_reason"],
                    quality["ffprobe_success"],
                ),
            )

    def _save_evidence(
        self,
        candidate: MediaCandidate,
        evidence: dict[str, Any],
    ) -> None:
        timestamp = self.now()
        with sqlite3.connect(self.db_path) as con:
            row = con.execute(
                "SELECT evidence_json FROM maccms_probe_result WHERE id=?",
                (candidate.probe_id,),
            ).fetchone()
            current = _safe_json(row[0] if row else "{}")
            current["media_attempt"] = evidence
            current["media_verified"] = bool(evidence.get("success"))
            con.execute(
                "UPDATE maccms_probe_result SET evidence_json=? WHERE id=?",
                (json.dumps(current, ensure_ascii=False, sort_keys=True), candidate.probe_id),
            )
            artifact_url = candidate.endpoint
            artifact = con.execute(
                "SELECT id,metadata_json FROM discovered_artifact "
                "WHERE connector='maccms' AND artifact_url=?",
                (artifact_url,),
            ).fetchone()
            if artifact:
                metadata = _safe_json(artifact[1])
                metadata.update({
                    "media_verified": bool(evidence.get("success")),
                    "last_media_attempt_at": timestamp,
                    "last_media_failure_stage": evidence.get("failure_stage"),
                    "media_fingerprint": candidate.fingerprint,
                })
                con.execute(
                    "UPDATE discovered_artifact SET metadata_json=?,last_seen_at=? WHERE id=?",
                    (
                        json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                        timestamp,
                        artifact[0],
                    ),
                )

    @staticmethod
    def _playback_failure_stage(url: str, result: dict[str, Any]) -> str | None:
        if not result.get("success"):
            if _is_hls(url) and not result.get("m3u8_ok"):
                return "media_manifest_failed"
            return "media_playback_failed"
        return None

    def _quality_result(
        self,
        candidate: MediaCandidate,
        play_url: str,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        raw = self.ffprobe_runner(play_url, request_headers=headers)
        info = media_quality.analyze_stream(raw)
        ffprobe_success = int(bool(info.get("success")))
        duration = media_quality.evaluate_duration(
            info.get("duration_s"), candidate.content_type
        )
        info.update(duration)
        if ffprobe_success and not duration["duration_pass"]:
            info["success"] = 0
            info["error"] = duration["duration_reason"]
        info["ffprobe_success"] = ffprobe_success
        return info

    def probe_candidate(self, candidate: MediaCandidate, run_id: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "raw_id": candidate.raw_id,
            "fingerprint": candidate.fingerprint,
            "endpoint": candidate.endpoint,
            "keyword": candidate.keyword,
            "title": candidate.title,
            "content_type": candidate.content_type,
            "quick_probe_ready": bool(candidate.sample_urls),
            "attempts": [],
            "success": False,
            "failure_stage": candidate.quick_failure_stage or "quick_probe_incomplete",
        }
        if not (
            candidate.search_ok and candidate.keyword_hit and candidate.detail_ok
            and candidate.playable_url_count > 0 and candidate.sample_urls
        ):
            self._save_test_rows(candidate, run_id, None, None, result["failure_stage"])
            self._save_evidence(candidate, result)
            return result

        headers = playback.parse_tvbox_headers(candidate.ext)
        final_playback: dict[str, Any] | None = None
        final_quality: dict[str, Any] | None = None
        final_url = candidate.sample_urls[0]
        for play_url in candidate.sample_urls:
            final_url = play_url
            url_evidence = {
                "play_url_sha256": hashlib.sha256(play_url.encode("utf-8")).hexdigest(),
                "play_url_host": urlsplit(play_url).hostname,
            }
            if not self.safety_check(play_url):
                url_evidence.update({"success": False, "failure_stage": "ssrf"})
                result["attempts"].append(url_evidence)
                result["failure_stage"] = "ssrf"
                continue
            playback_result = self.playback_check(play_url, mode="deep", ext_str=candidate.ext)
            playback_stage = self._playback_failure_stage(play_url, playback_result)
            url_evidence["playback"] = playback_result
            if playback_stage:
                if final_quality is None:
                    final_url = play_url
                    final_playback = playback_result
                url_evidence.update({"success": False, "failure_stage": playback_stage})
                result["attempts"].append(url_evidence)
                result["failure_stage"] = playback_stage
                continue
            quality = self._quality_result(candidate, play_url, headers)
            final_url = play_url
            final_playback = playback_result
            final_quality = quality
            url_evidence["quality"] = quality
            if quality.get("success"):
                url_evidence["success"] = True
                result["attempts"].append(url_evidence)
                result["success"] = True
                result["failure_stage"] = None
                break
            stage = (
                "duration_gate_failed"
                if quality.get("ffprobe_success")
                else "ffprobe_failed"
            )
            url_evidence.update({"success": False, "failure_stage": stage})
            result["attempts"].append(url_evidence)
            result["failure_stage"] = stage

        if final_quality is None:
            duration = media_quality.evaluate_duration(None, candidate.content_type)
            final_quality = {
                "success": 0,
                "error": (final_playback or {}).get("error") or result["failure_stage"],
                "width": None, "height": None, "video_codec": None,
                "video_bitrate": None, "audio_codec": None, "frame_rate": None,
                "duration_s": None, "quality_tier": None, "ffprobe_success": 0,
                **duration,
            }
        self._save_media_probe(candidate, final_url, final_quality)
        self._save_test_rows(
            candidate, run_id, final_playback, final_quality, result["failure_stage"]
        )
        self._save_evidence(candidate, result)
        return result

    def run(self, *, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
        candidates = load_candidates(self.db_path)
        selected = candidates[:max(1, min(int(limit), 100))]
        run_id = f"maccms-media-{uuid.uuid4().hex}"
        results = []
        for candidate in selected:
            try:
                results.append(self.probe_candidate(candidate, run_id))
            except Exception as exc:
                results.append({
                    "raw_id": candidate.raw_id,
                    "fingerprint": candidate.fingerprint,
                    "endpoint": candidate.endpoint,
                    "keyword": candidate.keyword,
                    "quick_probe_ready": bool(candidate.sample_urls),
                    "attempts": [],
                    "success": False,
                    "failure_stage": "bridge_exception",
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                })
        return {
            "generated_at": self.now(),
            "run_id": run_id,
            "connector": "maccms_media",
            "candidate_count": len(candidates),
            "selected_count": len(selected),
            "results": results,
            "summary": {
                "selected": len(selected),
                "quick_probe_ready": sum(
                    bool(item.get("quick_probe_ready")) for item in results
                ),
                "media_passed": sum(bool(item.get("success")) for item in results),
                "media_failed": sum(not bool(item.get("success")) for item in results),
                "failure_stages": {
                    stage: sum(item.get("failure_stage") == stage for item in results)
                    for stage in sorted({
                        str(item.get("failure_stage"))
                        for item in results if item.get("failure_stage")
                    })
                },
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DATA_DIR / "sources.db"))
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument(
        "--report", default=str(REPORT_DIR / "maccms-media-report.json")
    )
    args = parser.parse_args()
    report = MacCMSMediaBridge(args.db).run(limit=args.limit)
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
