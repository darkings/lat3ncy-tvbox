#!/usr/bin/env python3
import json
import sqlite3
from pathlib import Path

import pytest

from ponyo_source_manager.probes import probe_conn
from ponyo_source_manager.probes.probe_conn import (
    _approved_jar_rewrites,
    _group_urls,
    _is_trusted_drpy_api,
    _is_trusted_drpy_asset,
    _probe_trusted_drpy_asset,
    run_probe,
)


def test_trusted_drpy_probe_scope_is_exact():
    assert _is_trusted_drpy_api("http://127.0.0.1:5757/api/real-module")
    assert not _is_trusted_drpy_api("http://127.0.0.1:5757/config/1")
    assert not _is_trusted_drpy_api("http://localhost:5757/api/real-module")
    assert not _is_trusted_drpy_api("http://169.254.169.254:5757/api/real-module")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:5757/js/a.js",
        "http://127.0.0.1:5757/cat/a.js",
        "http://[::1]:5757/public/drpy/a.js",
    ],
)
def test_trusted_drpy_asset_scope_accepts_only_runtime_assets(url):
    assert _is_trusted_drpy_asset(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:5757/js/a.js",
        "http://127.0.0.1:9978/file/a.js",
        "http://127.0.0.1:5757/config/a.js",
        "http://user:pass@127.0.0.1:5757/js/a.js",
    ],
)
def test_trusted_drpy_asset_scope_rejects_other_local_urls(url):
    assert not _is_trusted_drpy_asset(url)


class _FakeResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def getcode(self):
        return self.status

    def read(self, _size=-1):
        return b"x"


def test_trusted_drpy_asset_probe_disables_proxy_and_redirects(monkeypatch):
    captured = {}

    class FakeOpener:
        def open(self, request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return _FakeResponse(200)

    def fake_build_opener(*handlers):
        captured["handlers"] = handlers
        return FakeOpener()

    monkeypatch.setattr(probe_conn.urllib.request, "build_opener", fake_build_opener)
    result = _probe_trusted_drpy_asset(
        "http://127.0.0.1:5757/js/a.js", now="2026-07-30T00:00:00+00:00"
    )

    assert result["ok"] == 1
    assert result["http_status"] == 200
    assert captured["timeout"] == 10.0
    assert any(
        isinstance(handler, probe_conn.urllib.request.ProxyHandler)
        and handler.proxies == {}
        for handler in captured["handlers"]
    )
    assert any(
        isinstance(handler, probe_conn._NoLocalRedirect)
        for handler in captured["handlers"]
    )


def test_trusted_drpy_asset_probe_records_404(monkeypatch):
    class FakeOpener:
        def open(self, request, timeout):
            raise probe_conn.urllib.error.HTTPError(
                request.full_url, 404, "not found", {}, None
            )

    monkeypatch.setattr(
        probe_conn.urllib.request, "build_opener", lambda *_handlers: FakeOpener()
    )
    result = _probe_trusted_drpy_asset(
        "http://127.0.0.1:5757/cat/missing.js",
        now="2026-07-30T00:00:00+00:00",
    )

    assert result["ok"] == 0
    assert result["http_status"] == 404
    assert result["err"] == "http: 404"


def _create_jar_tables(con):
    con.execute(
        "CREATE TABLE dependency_asset_evidence ("
        "fingerprint TEXT, effective_url TEXT, content_sha256 TEXT, asset_type TEXT)"
    )
    con.execute(
        "CREATE TABLE dependency_asset_approval ("
        "content_sha256 TEXT, asset_type TEXT, status TEXT, expires_at TEXT)"
    )


@pytest.mark.parametrize(
    ("status", "expires_at", "rewritten"),
    [
        ("approved", "2099-01-01T00:00:00+00:00", True),
        ("approved", "2020-01-01T00:00:00+00:00", False),
        ("revoked", "2099-01-01T00:00:00+00:00", False),
        ("rejected", "2099-01-01T00:00:00+00:00", False),
    ],
)
def test_approved_jar_rewrite_requires_live_approval(status, expires_at, rewritten):
    con = sqlite3.connect(":memory:")
    _create_jar_tables(con)
    sha256 = "a" * 64
    upstream = "https://cdn.jsdelivr.net/gh/owner/repo/spider.jar"
    con.execute(
        "INSERT INTO dependency_asset_evidence VALUES(?,?,?,?)",
        ("fp1", upstream, sha256, "jar"),
    )
    con.execute(
        "INSERT INTO dependency_asset_approval VALUES(?,?,?,?)",
        (sha256, "jar", status, expires_at),
    )

    result = _approved_jar_rewrites(
        con,
        now="2026-07-30T00:00:00+00:00",
        base_url="https://api.ponyo.fun/assets/jar",
    )
    expected = f"https://api.ponyo.fun/assets/jar/{sha256}.jar"
    assert (result.get(("fp1", upstream)) == expected) is rewritten


def test_approved_jar_rewrite_is_backward_compatible_without_tables():
    con = sqlite3.connect(":memory:")
    assert _approved_jar_rewrites(con, now="2026-07-30T00:00:00+00:00") == {}


def test_group_urls_replaces_only_the_approved_jar():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE norm_source (fingerprint TEXT, required_urls TEXT)")
    _create_jar_tables(con)
    sha256 = "b" * 64
    upstream = "https://cdn.jsdelivr.net/gh/owner/repo/spider.jar"
    api_url = "http://127.0.0.1:5757/api/source"
    con.execute(
        "INSERT INTO norm_source VALUES(?,?)",
        ("fp1", json.dumps([upstream, api_url])),
    )
    con.execute(
        "INSERT INTO dependency_asset_evidence VALUES(?,?,?,?)",
        ("fp1", upstream, sha256, "jar"),
    )
    con.execute(
        "INSERT INTO dependency_asset_approval VALUES(?,?,?,?)",
        (sha256, "jar", "approved", "2099-01-01T00:00:00+00:00"),
    )

    groups = _group_urls(
        con,
        now="2026-07-30T00:00:00+00:00",
        approved_asset_base_url="https://api.ponyo.fun/assets/jar",
    )
    assert groups["fp1"] == {
        f"https://api.ponyo.fun/assets/jar/{sha256}.jar",
        api_url,
    }


def test_file_service_is_not_in_either_trusted_drpy_scope():
    url = "http://127.0.0.1:9978/file/a.js"
    assert not _is_trusted_drpy_api(url)
    assert not _is_trusted_drpy_asset(url)


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
    con.execute(
        "INSERT INTO norm_source VALUES ('fp1', '[\"https://example.com/api\"]')"
    )
    con.commit()
    con.close()

    def mock_probe(url, now=None):
        return {
            "dns_ok": 1,
            "tcp_ok": 1,
            "tls_ok": 1,
            "http_status": 200,
            "latency_ms": 50,
            "ok": 1,
            "err": None,
            "probed_at": "2026-07-25T10:00:00Z",
        }

    res = run_probe(
        db_path, timeslot="morning", probe_fn=mock_probe, inter_host_delay=0
    )
    assert res["total_urls"] == 1
    assert res["ok"] == 1

    con = sqlite3.connect(str(db_path))
    rows = con.execute("SELECT * FROM conn_probe").fetchall()
    con.close()
    assert len(rows) == 1
    assert rows[0][1] == "fp1"


def test_run_probe_skips_recent_ok_urls_incrementally(tmp_path):
    """增量窗口内已成功探测的 URL 应跳过（失败/新增仍探测）。"""
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
    con.execute(
        "INSERT INTO norm_source VALUES "
        "('fp1', '[\"https://ok.example.com/a\", "
        '"https://new.example.com/b", "https://fail.example.com/c"]\')'
    )
    con.execute(
        "INSERT INTO conn_probe VALUES "
        "(1,'fp1','https://ok.example.com/a','morning',1,1,1,200,50,1,NULL,"
        "datetime('now'));"
    )
    con.execute(
        "INSERT INTO conn_probe VALUES "
        "(2,'fp1','https://fail.example.com/c','morning',1,1,1,500,50,0,'x',"
        "datetime('now','-1 hour'));"
    )
    con.commit()
    con.close()

    probed = []

    def mock_probe(url, now=None):
        probed.append(url)
        return {
            "dns_ok": 1,
            "tcp_ok": 1,
            "tls_ok": 1,
            "http_status": 200,
            "latency_ms": 50,
            "ok": 1,
            "err": None,
            "probed_at": "2026-07-25T10:00:00Z",
        }

    def reset_db():
        # 每轮独立验证：清掉上一轮 run_probe 写入的记录，恢复初始两行
        probed.clear()
        con = sqlite3.connect(str(db_path))
        con.execute("DELETE FROM conn_probe")
        con.execute(
            "INSERT INTO conn_probe VALUES "
            "(1,'fp1','https://ok.example.com/a','morning',1,1,1,200,50,1,NULL,"
            "datetime('now'));"
        )
        con.execute(
            "INSERT INTO conn_probe VALUES "
            "(2,'fp1','https://fail.example.com/c','morning',1,1,1,500,50,0,'x',"
            "datetime('now','-1 hour'));"
        )
        con.commit()
        con.close()

    # 默认组合（成功 24h + 失败 12h 冷却）：只探测新 URL b + 可能 1/4 轮转
    res = run_probe(
        db_path,
        timeslot="noon",
        probe_fn=mock_probe,
        inter_host_delay=0,
        max_age_hours=24.0,
        fail_cool_hours=12.0,
    )
    assert res["total_urls"] == 3
    assert res["skipped_recent_ok"] + res["rotated_reprobe"] == 1
    assert res["skipped_recent_fail"] == 1
    assert "https://fail.example.com/c" not in probed
    assert "https://new.example.com/b" in probed

    # 只开成功窗口（失败冷却关闭）：失败 URL 仍探测
    reset_db()
    res_ok_only = run_probe(
        db_path,
        timeslot="noon",
        probe_fn=mock_probe,
        inter_host_delay=0,
        max_age_hours=24.0,
        fail_cool_hours=0.0,
    )
    assert res_ok_only["skipped_recent_ok"] + res_ok_only["rotated_reprobe"] == 1
    assert res_ok_only["skipped_recent_fail"] == 0
    assert "https://fail.example.com/c" in probed

    # 只开失败冷却：ok URL 全量探测，失败 URL 跳过
    reset_db()
    res_fail_cool = run_probe(
        db_path,
        timeslot="noon",
        probe_fn=mock_probe,
        inter_host_delay=0,
        max_age_hours=0.0,
        fail_cool_hours=12.0,
    )
    assert res_fail_cool["probed"] == 2
    assert res_fail_cool["skipped_recent_fail"] == 1
    assert res_fail_cool["skipped_recent_ok"] == 0
    assert "https://fail.example.com/c" not in probed

    # 全量模式（两个窗口都关闭）探测所有 URL
    reset_db()
    res_full = run_probe(
        db_path,
        timeslot="noon",
        probe_fn=mock_probe,
        inter_host_delay=0,
        max_age_hours=0.0,
        fail_cool_hours=0.0,
    )
    assert res_full["probed"] == 3
    assert res_full["skipped_recent_ok"] == 0
    assert res_full["skipped_recent_fail"] == 0


def test_run_probe_rotates_one_fourth_of_recent_ok_urls(tmp_path):
    """冷却窗口内成功的 URL 按 hash 分片轮转重测 1/4，保证 4 时段覆盖。"""
    import hashlib as _hl

    db_path = tmp_path / "rot.db"
    con = sqlite3.connect(str(db_path))
    con.execute("""
        CREATE TABLE norm_source (fingerprint TEXT, required_urls TEXT)
    """)
    con.execute("""
        CREATE TABLE conn_probe (
            id INTEGER PRIMARY KEY, fingerprint TEXT, target_url TEXT,
            timeslot TEXT, dns_ok INT, tcp_ok INT, tls_ok INT,
            http_status INT, latency_ms INT, ok INT, err TEXT, probed_at TEXT
        )
    """)
    urls = [f"https://site{i}.example.com/api" for i in range(4)]
    con.execute(
        "INSERT INTO norm_source VALUES ('fp1', ?)",
        (json.dumps(urls),),
    )
    for i, u in enumerate(urls):
        con.execute(
            "INSERT INTO conn_probe VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (i + 1, "fp1", u, "morning", 1, 1, 1, 200, 50, 1, None, "datetime('now')"),
        )
    con.commit()
    con.close()

    probed = []

    def mock_probe(url, now=None):
        probed.append(url)
        return {
            "dns_ok": 1,
            "tcp_ok": 1,
            "tls_ok": 1,
            "http_status": 200,
            "latency_ms": 50,
            "ok": 1,
            "err": None,
            "probed_at": "2026-07-25T10:00:00Z",
        }

    # noon 时段：hash % 4 == 1 的 URL 应被轮转重测
    expected_rotate = [
        u for u in urls if int(_hl.md5(u.encode()).hexdigest(), 16) % 4 == 1
    ]
    res = run_probe(
        db_path,
        timeslot="noon",
        probe_fn=mock_probe,
        inter_host_delay=0,
        max_age_hours=24.0,
        fail_cool_hours=0.0,
    )
    assert res["rotated_reprobe"] == 1
    assert len(expected_rotate) == 1
    assert expected_rotate[0] in probed
    assert res["probed"] == 1
    assert res["skipped_recent_ok"] == 3

    # night 时段：hash % 4 == 3 的 URL 被轮转重测
    expected_night = [
        u for u in urls if int(_hl.md5(u.encode()).hexdigest(), 16) % 4 == 3
    ]
    res_night = run_probe(
        db_path,
        timeslot="night",
        probe_fn=mock_probe,
        inter_host_delay=0,
        max_age_hours=24.0,
        fail_cool_hours=0.0,
    )
    assert res_night["rotated_reprobe"] == 1
    assert len(expected_night) == 1
    assert expected_night[0] in probed
