from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from ponyo_source_manager.core.initdb import init_db
from ponyo_source_manager.probes.drpy_runner import (
    _evidence_json,
    classify_failure_stage,
    save_results,
)


def test_failure_taxonomy_is_stable_and_platform_pages_fail_closed():
    assert classify_failure_stage({
        "test_type": "search", "success": 0, "result_count": 0, "error": None,
    })["failure_stage"] == "search_empty"
    assert classify_failure_stage({
        "test_type": "detail", "success": 0, "result_count": 0,
        "error": "timeout after 15s",
    })["failure_stage"] == "detail_timeout"
    play = classify_failure_stage({
        "test_type": "playurl", "success": 1, "result_count": 1,
        "play_url": "https://v.qq.com/x/cover/abc.html", "error": None,
    })
    assert play["success"] == 0
    assert play["failure_stage"] == "platform_page"


@pytest.mark.parametrize(
    ("error", "signature", "disposition"),
    [
        (
            "drpy2 runner error: rule must point to a drpy-node /api/:module endpoint",
            "drpy_endpoint_required",
            "configuration",
        ),
        ("drpy2 runner error: Invalid URL", "invalid_url", "configuration"),
        (
            "drpy2 runner error: T4 search returned an empty list",
            "t4_search_empty",
            "upstream_empty",
        ),
        ("drpy2 runner error: T4 HTTP 500", "t4_http_500", "upstream_server"),
    ],
)
def test_search_runtime_errors_receive_stable_second_level_signatures(
    error, signature, disposition,
):
    result = classify_failure_stage({
        "test_type": "search",
        "success": 0,
        "result_count": 0,
        "error": error,
    })

    assert result["failure_stage"] == "search_runtime_error"
    assert result["failure_signature"] == signature
    assert result["failure_disposition"] == disposition

    evidence = json.loads(_evidence_json(result))
    assert evidence["failure_signature"] == signature
    assert evidence["failure_disposition"] == disposition
    assert "error" not in evidence


def test_media_failure_stages_are_separate():
    manifest = classify_failure_stage({
        "test_type": "playback", "success": 0,
        "error": "m3u8 fetch failed: timeout",
    })
    assert manifest["failure_stage"] == "playback_timeout"
    segments = classify_failure_stage({
        "test_type": "playback", "success": 0, "m3u8_ok": 1,
        "segments_checked": 3, "segments_ok": 0, "error": "segment download failed",
    })
    assert segments["failure_stage"] == "media_segment_failed"
    duration = classify_failure_stage({
        "test_type": "ffprobe", "success": 0, "ffprobe_success": 1,
        "duration_pass": 0, "error": "duration below gate",
    })
    assert duration["failure_stage"] == "duration_gate_failed"


def test_extended_evidence_persists_run_and_stage_without_sensitive_url(tmp_path: Path):
    db = tmp_path / "sources.db"
    init_db(str(db))
    result = classify_failure_stage({
        "test_type": "playback", "keyword": "测试", "success": 0,
        "m3u8_ok": 1, "segments_total": 3, "segments_checked": 1,
        "segments_ok": 0, "latency_ms": 123,
        "play_url": "https://media.test/video.m3u8?token=secret",
        "error": "segment download failed",
    })
    assert save_results(
        str(db), "fp-evidence", [result], now="2026-07-28T00:00:00Z",
        run_id="run-evidence", adapter_version="adapter-test",
    ) == 1
    with sqlite3.connect(db) as con:
        row = con.execute(
            "SELECT failure_stage,run_id,adapter_version,evidence_json "
            "FROM drpy_test_result WHERE fingerprint='fp-evidence'"
        ).fetchone()
        run_table = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='drpy_run'"
        ).fetchone()
    assert row[:3] == ("media_segment_failed", "run-evidence", "adapter-test")
    evidence = json.loads(row[3])
    assert evidence["segments_checked"] == 1
    assert "play_url" not in evidence
    assert "secret" not in row[3]
    assert run_table == ("drpy_run",)
