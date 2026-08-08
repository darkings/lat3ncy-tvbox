#!/usr/bin/env python3
import json
import sqlite3
import pytest
from ponyo_source_manager.probes.drpy_runner import run_drpy_search, run_drpy_detail, run_drpy_episode, run_drpy_playurl, run_full_chain, save_results, select_rule_path


def mock_runner(rule, action, params):
    if action == "search":
        return {"list": [{"id": "123", "vod_name": "测试影片"}]}
    elif action == "detail":
        return {"title": "测试影片", "vod_id": "123"}
    elif action == "episode":
        return {"list": [{"url": "http://example.com/play/1.m3u8"}]}
    elif action == "play":
        return {"url": "http://example.com/stream/1.m3u8"}
    return {}


def test_drpy_full_chain(monkeypatch):
    from ponyo_source_manager.probes import playback
    from ponyo_source_manager.probes import media_quality
    monkeypatch.setattr(playback, "verify_playback", lambda u, **k: {"success": 1, "m3u8_ok": 1, "segments_total": 1, "segments_checked": 1, "latency_ms": 100, "error": None})
    monkeypatch.setattr(media_quality, "probe_and_save", lambda fp, u, **k: {"success": 1})
    results = run_full_chain("rule.js", "测试", runner=mock_runner)
    assert len(results) == 5
    assert all(r["success"] == 1 for r in results)

def test_save_results(tmp_path, monkeypatch):
    from ponyo_source_manager.probes import playback
    from ponyo_source_manager.probes import media_quality
    monkeypatch.setattr(playback, "verify_playback", lambda u, **k: {"success": 1, "m3u8_ok": 1, "segments_total": 1, "segments_checked": 1, "latency_ms": 100, "error": None})
    monkeypatch.setattr(media_quality, "probe_and_save", lambda fp, u, **k: {"success": 1})
    db_path = tmp_path / "test.db"
    con = sqlite3.connect(str(db_path))
    con.execute("""
        CREATE TABLE drpy_test_result (
            id INTEGER PRIMARY KEY, fingerprint TEXT, test_type TEXT,
            keyword TEXT, success INT, result_count INT, latency_ms INT,
            error TEXT, tested_at TEXT
        )
    """)
    con.commit()
    con.close()

    chain = run_full_chain("rule.js", "测试", runner=mock_runner)
    count = save_results(db_path, "fp_drpy", chain, now="2026-07-25T10:00:00Z")
    assert count == 5

    con = sqlite3.connect(str(db_path))
    rows = con.execute("SELECT test_type FROM drpy_test_result WHERE fingerprint='fp_drpy'").fetchall()
    con.close()
    assert len(rows) == 5


def test_production_runner_rejects_placeholder_response(monkeypatch):
    from types import SimpleNamespace
    from ponyo_source_manager.probes import drpy_runner

    monkeypatch.setattr(
        drpy_runner.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            returncode=0,
            stdout='{"url":"http://example.com/mock.m3u8"}',
            stderr="",
        ),
    )
    result = drpy_runner._run_drpy("rule.js", "play", {"flag": "x"})
    assert result["success"] is False
    assert "placeholder" in result["error"]


def test_node_bridge_requires_real_adapter():
    from pathlib import Path

    bridge = Path(__file__).resolve().parents[1] / "drpy2" / "index.js"
    text = bridge.read_text(encoding="utf-8")
    assert "DRPY2_ADAPTER" in text
    assert "example.com/mock.m3u8" not in text


def test_select_rule_path_uses_resolved_drpy2_ext():
    assert select_rule_path(
        "./libs/drpy2.min.js",
        "./js/儿童.js",
        "https://raw.example/box/config/main.json",
    ) == "https://raw.example/box/config/js/儿童.js"


def test_select_rule_path_keeps_drpys_endpoint():
    endpoint = "http://127.0.0.1:5757/api/影视?pwd=secret"
    assert select_rule_path(endpoint, "./unused.js", endpoint) == endpoint
