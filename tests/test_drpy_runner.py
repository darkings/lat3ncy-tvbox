#!/usr/bin/env python3
import json
import sqlite3
import pytest
from drpy_runner import run_drpy_search, run_drpy_detail, run_drpy_episode, run_drpy_playurl, run_full_chain, save_results


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


def test_drpy_full_chain():
    results = run_full_chain("rule.js", "测试", runner=mock_runner)
    assert len(results) == 4
    assert all(r["success"] == 1 for r in results)


def test_save_results(tmp_path):
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
    assert count == 4

    con = sqlite3.connect(str(db_path))
    rows = con.execute("SELECT test_type FROM drpy_test_result WHERE fingerprint='fp_drpy'").fetchall()
    con.close()
    assert len(rows) == 4
