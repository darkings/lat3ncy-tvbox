import json
import sqlite3

import pytest

from ponyo_source_manager.core import initdb
from ponyo_source_manager.probes import scan_security as ss

RULES = [
    {"rule_id": "system-exit", "severity": "high", "pattern": r"System\.exit"},
    {
        "rule_id": "cleartext-secret",
        "severity": "high",
        "pattern": r"(?i)token\s*=\s*[A-Za-z0-9]{8,}",
    },
]


def test_match_detects_system_exit():
    hits = ss.match_text_rules("if(x){System.exit(0);}", RULES)
    ids = {h["rule_id"] for h in hits}
    assert "system-exit" in ids


def test_sanitize_masks_token():
    ev = ss.sanitize_evidence("k token=ABCD1234EFGH tail", 2, 22)
    assert "ABCD1234EFGH" not in ev and "****" in ev and "\n" not in ev


def test_check_jar_md5_mismatch_high():
    f = ss.check_jar_md5("deadbeef", b"real-bytes", "x.com", set())
    assert f and f["severity"] == "high" and f["rule_id"] == "jar-md5-mismatch"


def test_check_jar_md5_unverified_medium():
    f = ss.check_jar_md5("", b"j", "evil.com", {"cdn.jsdelivr.net"})
    assert f and f["severity"] == "medium" and f["rule_id"] == "jar-unverified"


def test_check_jar_md5_match_returns_none():
    import hashlib

    good = hashlib.md5(b"j").hexdigest()
    assert ss.check_jar_md5(good, b"j", "x.com", set()) is None


def test_sanitize_masks_underscore_token():
    ev = ss.sanitize_evidence("x password=ghp_1A2b3C4d5E6f7G8h9I0j tail", 2, 40)
    assert "ghp_1A2b3C4d5E6f7G8h9I0j" not in ev and "****" in ev


def test_sanitize_masks_dotted_and_dashed():
    ev1 = ss.sanitize_evidence("token=aaa.bbb.ccc-ddd end", 0, 22)
    assert "aaa.bbb.ccc-ddd" not in ev1 and "****" in ev1


def test_check_jar_md5_unpinned_low():
    f = ss.check_jar_md5("", b"j", "cdn.jsdelivr.net", {"cdn.jsdelivr.net"})
    assert f and f["severity"] == "low" and f["rule_id"] == "jar-unpinned"


def test_jar_fetch_candidates_jsdelivr_prefers_verified_proxy():
    c = ss._jar_fetch_candidates(
        "https://cdn.jsdelivr.net/gh/gaotianliuyun/gao@master/jar/pg.jar"
    )
    assert c[0] == (
        "https://gh-proxy.com/"
        "https://raw.githubusercontent.com/gaotianliuyun/gao/master/jar/pg.jar"
    )
    assert c[1] == (
        "https://raw.githubusercontent.com/gaotianliuyun/gao/master/jar/pg.jar"
    )
    assert c[2] == ("https://cdn.jsdelivr.net/gh/gaotianliuyun/gao@master/jar/pg.jar")
    assert len(c) == 3


def test_jar_fetch_candidates_raw_input_prefers_verified_proxy():
    c = ss._jar_fetch_candidates("https://raw.githubusercontent.com/a/b/main/x.jar")
    assert (
        c[0] == "https://gh-proxy.com/https://raw.githubusercontent.com/a/b/main/x.jar"
    )
    assert c[1] == "https://raw.githubusercontent.com/a/b/main/x.jar"
    assert len(c) == 2


def test_jar_fetch_candidates_other_url_unchanged():
    assert ss._jar_fetch_candidates("https://example.com/x.jar") == [
        "https://example.com/x.jar"
    ]


def test_jar_fetch_candidates_liucn_falls_back_to_github_mirror():
    c = ss._jar_fetch_candidates("https://raw.liucn.cc/box/libs/jar/XBPQ.jar")
    assert c[0] == "https://raw.liucn.cc/box/libs/jar/XBPQ.jar"
    assert c[1] == (
        "https://gh-proxy.com/"
        "https://raw.githubusercontent.com/liu673cn/box/main/libs/jar/XBPQ.jar"
    )
    assert c[2] == (
        "https://raw.githubusercontent.com/liu673cn/box/main/libs/jar/XBPQ.jar"
    )
    assert len(c) == 3


def test_fetch_jar_aborts_on_http_404_without_trying_fallbacks():
    """404 是确定性结果：不应继续尝试 raw 直连（60s 超时）。"""
    import urllib.error

    attempts = []

    def fake_fetch(url, timeout=60.0, max_bytes=None):
        attempts.append(url)
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)

    with pytest.raises(RuntimeError) as exc:
        ss._fetch_jar(fake_fetch, "https://cdn.jsdelivr.net/gh/a/b@main/jar/x.jar")
    assert "HTTP 404" in str(exc.value)
    assert len(attempts) == 1  # 只尝试了 gh-proxy，未回退 raw


def test_fetch_jar_timeout_still_tries_fallbacks():
    """非 404 失败（如超时）仍按顺序尝试后续候选。"""
    attempts = []

    def fake_fetch(url, timeout=60.0, max_bytes=None):
        attempts.append(url)
        if len(attempts) == 1:
            raise TimeoutError("timeout")
        return b"PK\x03\x04ok"

    payload, used = ss._fetch_jar(
        fake_fetch, "https://cdn.jsdelivr.net/gh/a/b@main/jar/x.jar"
    )
    assert payload == b"PK\x03\x04ok"
    assert len(attempts) == 2
    assert used == attempts[1]


def _seed(db, rows):
    initdb.init_db(str(db))
    con = sqlite3.connect(str(db))
    for raw_id, fp, urls, jar_md5 in rows:
        con.execute(
            "INSERT INTO raw_source(id,import_batch,origin,site_key,raw_json)"
            " VALUES(?,?,?,?,?)",
            (raw_id, "b", "o", f"k{raw_id}", "{}"),
        )
        con.execute(
            "INSERT INTO norm_source(raw_id,fingerprint,api_host,required_urls,"
            "jar_md5,spider_class,category,capabilities) VALUES(?,?,?,?,?,?,?,?)",
            (raw_id, fp, "h", json.dumps(urls), jar_md5, "", "影视", "[]"),
        )
        con.execute(
            "INSERT OR IGNORE INTO list_state(fingerprint,state,reason,updated_at)"
            " VALUES(?,?,?,?)",
            (fp, "candidate", "", "T"),
        )
    con.commit()
    con.close()


def test_run_scan_flags_high_and_denies(tmp_path):
    db = tmp_path / "s.db"
    _seed(db, [(1, "fp1", ["https://x.com/rule.js"], "")])
    rules = tmp_path / "r.json"
    rules.write_text(
        json.dumps(
            [
                {
                    "rule_id": "suspect-SystemExit",
                    "severity": "high",
                    "pattern": r"System\.exit",
                }
            ]
        ),
        encoding="utf-8",
    )
    allow = tmp_path / "a.json"
    allow.write_text("[]", encoding="utf-8")
    rep = tmp_path / "sec.json"
    res = ss.run_scan(
        str(db),
        str(rules),
        str(allow),
        str(rep),
        fetch_text=lambda u: "x=1;System.exit(0);",
        fetch_bytes=lambda u: b"",
        now="T",
    )
    assert res["high"] == 1 and "fp1" in res["deny_fps"]
    con = sqlite3.connect(str(db))
    state = con.execute(
        "SELECT state FROM list_state WHERE fingerprint='fp1'"
    ).fetchone()[0]
    con.close()
    assert state == "deny"
    assert json.loads(rep.read_text(encoding="utf-8"))["summary"]["high"] == 1


def _scan_files(tmp_path):
    rules = tmp_path / "rules.json"
    allow = tmp_path / "allow.json"
    report = tmp_path / "report.json"
    rules.write_text("[]", encoding="utf-8")
    allow.write_text("[]", encoding="utf-8")
    return rules, allow, report


def test_dynamic_local_api_is_not_treated_as_static_code(tmp_path):
    db = tmp_path / "s.db"
    url = "http://127.0.0.1:5757/api/source?pwd=x"
    _seed(db, [(1, "fp1", [url], "")])
    rules, allow, report = _scan_files(tmp_path)

    result = ss.run_scan(
        str(db),
        str(rules),
        str(allow),
        str(report),
        fetch_text=lambda _url: (_ for _ in ()).throw(
            AssertionError("dynamic API must not be fetched by static scanner")
        ),
    )

    assert result["skipped_dynamic_urls"] == 1
    assert result["fetch_errors"] == 0


def test_transient_jar_failure_retains_prior_invalid_result(tmp_path):
    db = tmp_path / "s.db"
    url = "https://assets.test/HCCX.jar"
    _seed(db, [(1, "fp1", [url], "")])
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO dependency_asset_evidence"
            "(fingerprint,config_origin,source_field,effective_url,asset_type,"
            "resolution_status,fetch_status,validation_status,first_seen_at,last_seen_at) "
            "VALUES('fp1','origin','site.jar',?,'jar','resolved','fetched',"
            "'invalid','T','T')",
            (url,),
        )
    rules, allow, report = _scan_files(tmp_path)

    result = ss.run_scan(
        str(db),
        str(rules),
        str(allow),
        str(report),
        fetch_bytes=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            TimeoutError("temporary timeout")
        ),
    )

    with sqlite3.connect(db) as con:
        row = con.execute(
            "SELECT fetch_status,validation_status,last_error "
            "FROM dependency_asset_evidence WHERE fingerprint='fp1'"
        ).fetchone()
    assert result["jar_fetch_errors"] == 1
    assert result["retained_prior_jar_results"] == 1
    assert row[0] == "failed"
    assert row[1] == "invalid"
    assert "temporary timeout" in row[2]


def test_approved_jar_reads_local_materialized_cache(tmp_path, monkeypatch):
    """已批准 jar 应从本地 approved-assets 缓存读取，不触发网络下载。"""
    import hashlib as _hashlib

    jar_bytes = b"PK\x03\x04fake-jar-content"
    sha256 = _hashlib.sha256(jar_bytes).hexdigest()
    approved_dir = tmp_path / "approved-assets" / "jar"
    approved_dir.mkdir(parents=True)
    (approved_dir / f"{sha256}.jar").write_bytes(jar_bytes)
    monkeypatch.setattr(ss, "APPROVED_JAR_DIR", approved_dir)

    db = tmp_path / "s.db"
    url = "https://assets.test/app.jar"
    _seed(db, [(1, "fp1", [url], "")])
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO dependency_asset_evidence"
            "(fingerprint,config_origin,source_field,effective_url,asset_type,"
            "resolution_status,fetch_status,validation_status,content_sha256,"
            "first_seen_at,last_seen_at) "
            "VALUES('fp1','origin','site.jar',?,'jar','resolved','fetched',"
            "'review_required',?,'T','T')",
            (url, sha256),
        )
    rules, allow, report = _scan_files(tmp_path)

    result = ss.run_scan(
        str(db),
        str(rules),
        str(allow),
        str(report),
        fetch_bytes=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("approved jar must not be downloaded")
        ),
    )

    assert result["jar_fetch_errors"] == 0
    with sqlite3.connect(db) as con:
        row = con.execute(
            "SELECT fetch_status,validation_status,last_error "
            "FROM dependency_asset_evidence WHERE fingerprint='fp1'"
        ).fetchone()
    assert row[0] == "fetched"
    assert row[2] is None
    assert "AssertionError" not in str(result)
