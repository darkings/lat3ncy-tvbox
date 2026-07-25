#!/usr/bin/env python3
import json
import sqlite3
import pytest
from pathlib import Path

from probe_conn import run_probe


def test_run_probe_mock(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    con = sqlite3.connect(str(db_path))
    con.execute("""
        CREATE TABLE norm_source (
            fingerprint TEXT, required_urls TEXT
        )
    """)
    con.execute("""
        CREATE TABLE conn_probe (
            id INTEGER PRIMARY KEY, fingerprint TEXT, target_url TEXT,
            timeslot TEXT, dns_ok INT, tcp_ok INT, tls_ok INT,
            http_status INT, latency_ms INT, ok INT, err TEXT, probed_at TEXT
        )
    """)
    con.execute("INSERT INTO norm_source VALUES ('fp1', '[\"https://example.com/api\"]')")
    con.commit()
    con.close()

    def mock_probe(url, now=None):
        return {
            "dns_ok": 1, "tcp_ok": 1, "tls_ok": 1,
            "http_status": 200, "latency_ms": 50,
            "ok": 1, "err": None, "probed_at": "2026-07-25T10:00:00Z"
        }

    res = run_probe(db_path, timeslot="morning", probe_fn=mock_probe, inter_host_delay=0)
    assert res["total_urls"] == 1
    assert res["ok"] == 1

    con = sqlite3.connect(str(db_path))
    rows = con.execute("SELECT * FROM conn_probe").fetchall()
    con.close()
    assert len(rows) == 1
    assert rows[0][1] == "fp1"
