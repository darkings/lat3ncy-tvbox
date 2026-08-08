import base64
import hashlib
import io
import json
import sqlite3
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

from ponyo_source_manager.core import initdb
from ponyo_source_manager.discovery.discover_sources import DiscoveryEngine
from ponyo_source_manager.discovery.path_resolver import collect_dependency_assets
from ponyo_source_manager.probes import scan_security
from ponyo_source_manager.probes.dependency_approval import (
    approve_asset,
    build_review_report,
    set_asset_decision,
    verify_github_provenance,
)
from ponyo_source_manager.scoring.scorer import compute_dependency_gate


def _jar_bytes(*, embedded_binary: bool = False) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
        archive.writestr("com/example/Spider.class", b"\xca\xfe\xba\xbe")
        if embedded_binary:
            archive.writestr("payload/classes.dex", b"dex\n")
    return buffer.getvalue()


def _verified_provenance(sha256: str):
    return lambda _repo, _commit, path: {
        "upstream_path": path,
        "git_blob_sha": "e" * 40,
        "content_sha256": sha256,
        "size_bytes": 1,
    }


def _seed_dependency_db(tmp_path, *, declared_md5: str, url: str):
    db = tmp_path / "sources.db"
    initdb.init_db(str(db))
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO raw_source"
        "(id,import_batch,origin,site_key,name,type,api,ext,raw_json) "
        "VALUES(1,'b','https://config.example/box.json','site','Site',3,"
        "'csp_Test','',?)",
        (json.dumps({"key": "site", "api": "csp_Test"}),),
    )
    con.execute(
        "INSERT INTO norm_source"
        "(raw_id,fingerprint,api_host,required_urls,jar_md5,spider_class,category,capabilities) "
        "VALUES(1,'fp1','',?,?,'csp_Test','normal','[]')",
        (json.dumps([url]), declared_md5),
    )
    con.execute(
        "INSERT INTO list_state(fingerprint,state,reason,updated_at) "
        "VALUES('fp1','candidate','test','T')"
    )
    con.execute(
        "INSERT INTO dependency_asset_evidence"
        "(fingerprint,config_origin,source_field,effective_url,asset_type,"
        "declared_md5,resolution_status,inherited_from_root,fetch_status,"
        "validation_status,first_seen_at,last_seen_at) "
        "VALUES('fp1','https://config.example/box.json','config.spider',?,"
        "'jar',?,'resolved',1,'pending','pending','T','T')",
        (url, declared_md5),
    )
    con.commit()
    con.close()
    rules = tmp_path / "rules.json"
    allowlist = tmp_path / "allowlist.json"
    report = tmp_path / "security.json"
    rules.write_text("[]", encoding="utf-8")
    allowlist.write_text("[]", encoding="utf-8")
    return db, rules, allowlist, report


def test_root_relative_spider_is_inherited_and_md5_is_case_insensitive():
    digest = "0123456789abcdef0123456789abcdef"
    records = collect_dependency_assets(
        "https://cdn.example/tv/config/box.json",
        {"key": "demo", "api": "csp_Demo"},
        {"spider": f"./jar/spider.jar;MD5;{digest}"},
    )

    assert records == [
        {
            "source_field": "config.spider",
            "effective_url": "https://cdn.example/tv/config/jar/spider.jar",
            "asset_type": "jar",
            "declared_md5": digest,
            "resolution_status": "resolved",
            "inherited_from_root": True,
        }
    ]


def test_jar_fetch_falls_back_between_jsdelivr_and_github_raw():
    requested = []
    request_options = []

    def fetch(url, **kwargs):
        requested.append(url)
        request_options.append(kwargs)
        if "cdn.jsdelivr.net" in url:
            raise OSError("cdn unavailable")
        if "gh-proxy.com" in url:
            raise OSError("proxy unavailable")
        return b"jar"

    payload, fetched_url = scan_security._fetch_jar(
        fetch,
        "https://cdn.jsdelivr.net/gh/owner/repo@main/jar/spider.jar",
    )
    assert payload == b"jar"
    # gh-proxy.com 优先（jsdelivr 对 .jar 全 403，raw 在无代理环境太慢）；
    # jsdelivr 在生成候选列表中作兼底，但 raw 在本测试中成功，故不需要走第三个候选。
    assert requested == [
        "https://gh-proxy.com/"
        "https://raw.githubusercontent.com/owner/repo/main/jar/spider.jar",
        "https://raw.githubusercontent.com/owner/repo/main/jar/spider.jar",
    ]
    assert (
        fetched_url
        == "https://raw.githubusercontent.com/owner/repo/main/jar/spider.jar"
    )
    assert request_options == [
        {
            "timeout": scan_security.JAR_FETCH_TIMEOUT_SECONDS,
            "max_bytes": scan_security.MAX_JAR_BYTES,
        },
        {
            "timeout": scan_security.JAR_FETCH_TIMEOUT_SECONDS,
            "max_bytes": scan_security.MAX_JAR_BYTES,
        },
    ]


def test_github_provenance_verifies_immutable_blob_content():
    payload = b"immutable jar bytes"
    encoded = base64.b64encode(payload).decode()
    responses = [
        {"type": "file", "sha": "a" * 40, "git_url": "https://api.github.com/blob"},
        OSError("incomplete first blob response"),
        {"encoding": "base64", "content": encoded[:8] + "\n" + encoded[8:]},
    ]

    def fetch(_url, **_kwargs):
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return json.dumps(response)

    result = verify_github_provenance(
        "owner/repository", "b" * 40, "jar/spider.jar", fetch_text=fetch
    )
    assert result == {
        "upstream_path": "jar/spider.jar",
        "git_blob_sha": "a" * 40,
        "content_sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }


def test_unchanged_config_backfills_dependencies_without_new_candidate(tmp_path):
    db = tmp_path / "sources.db"
    initdb.init_db(str(db))
    engine = DiscoveryEngine(str(db), "config/policy.json")
    batch_id = engine.start_batch("test")
    digest = "a" * 32
    config = {
        "spider": f"./jar/spider.jar;md5;{digest}",
        "sites": [{"key": "demo", "name": "Demo", "type": 3, "api": "csp_Demo"}],
    }
    fetch = lambda *_args, **_kwargs: json.dumps(config)

    first = engine.process_url_source(
        "https://config.example/tv/box.json",
        "test",
        batch_id,
        fetch_fn=fetch,
        now="2026-07-30T00:00:00+00:00",
        trusted_local=True,
    )
    con = sqlite3.connect(db)
    fingerprint = con.execute("SELECT fingerprint FROM norm_source").fetchone()[0]
    con.execute("DELETE FROM dependency_asset_evidence")
    con.execute("UPDATE norm_source SET required_urls='[]',jar_md5='' ")
    con.commit()
    con.close()

    second = engine.process_url_source(
        "https://config.example/tv/box.json",
        "test",
        batch_id,
        fetch_fn=fetch,
        now="2026-07-30T01:00:00+00:00",
        trusted_local=True,
    )
    con = sqlite3.connect(db)
    raw_count = con.execute("SELECT COUNT(*) FROM raw_source").fetchone()[0]
    dependency = con.execute(
        "SELECT effective_url,declared_md5,inherited_from_root "
        "FROM dependency_asset_evidence WHERE fingerprint=?",
        (fingerprint,),
    ).fetchone()
    required_urls, jar_md5 = con.execute(
        "SELECT required_urls,jar_md5 FROM norm_source WHERE fingerprint=?",
        (fingerprint,),
    ).fetchone()
    state = con.execute(
        "SELECT state FROM list_state WHERE fingerprint=?", (fingerprint,)
    ).fetchone()[0]
    con.close()

    assert first["added"] == 1
    assert second["added"] == 0
    assert second["skipped"] == 1
    assert second["dependency_assets"] == 1
    assert raw_count == 1
    assert dependency == ("https://config.example/tv/jar/spider.jar", digest, 1)
    assert json.loads(required_urls) == ["https://config.example/tv/jar/spider.jar"]
    assert jar_md5 == digest
    assert state == "candidate"


def test_valid_pinned_jar_is_verified_and_dependency_gate_passes(tmp_path):
    payload = _jar_bytes()
    digest = hashlib.md5(payload).hexdigest()
    url = "https://assets.example/spider.jar"
    db, rules, allowlist, report = _seed_dependency_db(
        tmp_path, declared_md5=digest, url=url
    )

    summary = scan_security.run_scan(
        str(db),
        str(rules),
        str(allowlist),
        str(report),
        fetch_bytes=lambda *_args, **_kwargs: payload,
        now="2026-07-30T00:00:00+00:00",
    )

    con = sqlite3.connect(db)
    evidence = con.execute(
        "SELECT fetch_status,fetched_url,actual_md5,validation_status "
        "FROM dependency_asset_evidence WHERE fingerprint='fp1'"
    ).fetchone()
    gate = compute_dependency_gate(con, "fp1")
    con.close()
    assert summary["jar_verified"] == 1
    assert evidence == ("fetched", url, digest, "verified")
    assert gate["complete"] is True


def test_jar_only_skips_text_and_preserves_existing_text_findings(tmp_path):
    payload = _jar_bytes()
    digest = hashlib.md5(payload).hexdigest()
    url = "https://assets.example/spider.jar"
    db, rules, allowlist, report = _seed_dependency_db(
        tmp_path, declared_md5=digest, url=url
    )
    con = sqlite3.connect(db)
    con.execute(
        "UPDATE norm_source SET required_urls=? WHERE fingerprint='fp1'",
        (json.dumps([url, "https://assets.example/rule.js"]),),
    )
    con.execute(
        "INSERT INTO security_finding"
        "(fingerprint,target_url,asset_type,rule_id,severity,evidence,scanned_at) "
        "VALUES('fp1','https://assets.example/rule.js','js','old-js',"
        "'low','keep','T')"
    )
    con.commit()
    con.close()

    def unexpected_text_fetch(*_args, **_kwargs):
        raise AssertionError("JAR-only mode fetched a text dependency")

    summary = scan_security.run_scan(
        str(db),
        str(rules),
        str(allowlist),
        str(report),
        fetch_text=unexpected_text_fetch,
        fetch_bytes=lambda *_args, **_kwargs: payload,
        jar_only=True,
        now="2026-07-30T00:00:00+00:00",
    )
    con = sqlite3.connect(db)
    retained = con.execute(
        "SELECT COUNT(*) FROM security_finding WHERE rule_id='old-js'"
    ).fetchone()[0]
    con.close()
    assert summary["jar_verified"] == 1
    assert summary["fetch_errors"] == 0
    assert retained == 1


def test_jar_md5_mismatch_is_high_and_denied(tmp_path):
    payload = _jar_bytes()
    url = "https://assets.example/spider.jar"
    db, rules, allowlist, report = _seed_dependency_db(
        tmp_path, declared_md5="0" * 32, url=url
    )
    summary = scan_security.run_scan(
        str(db),
        str(rules),
        str(allowlist),
        str(report),
        fetch_bytes=lambda *_args, **_kwargs: payload,
        now="2026-07-30T00:00:00+00:00",
    )
    con = sqlite3.connect(db)
    status = con.execute(
        "SELECT validation_status FROM dependency_asset_evidence"
    ).fetchone()[0]
    state = con.execute(
        "SELECT state FROM list_state WHERE fingerprint='fp1'"
    ).fetchone()[0]
    con.close()
    assert summary["high"] >= 1
    assert status == "invalid"
    assert state == "deny"


def test_non_zip_unpinned_fetch_failure_and_embedded_binary_never_verify(tmp_path):
    invalid = scan_security.inspect_jar_bytes("0" * 32, b"not-a-jar", "x", set())
    embedded_payload = _jar_bytes(embedded_binary=True)
    embedded = scan_security.inspect_jar_bytes(
        hashlib.md5(embedded_payload).hexdigest(), embedded_payload, "x", set()
    )
    unpinned = scan_security.inspect_jar_bytes("", _jar_bytes(), "x", set())
    assert invalid["validation_status"] == "invalid"
    assert embedded["validation_status"] == "review_required"
    assert unpinned["validation_status"] == "unpinned"

    url = "https://assets.example/spider.jar"
    db, rules, allowlist, report = _seed_dependency_db(
        tmp_path, declared_md5="0" * 32, url=url
    )

    def fail(*_args, **_kwargs):
        raise TimeoutError("download timeout")

    summary = scan_security.run_scan(
        str(db),
        str(rules),
        str(allowlist),
        str(report),
        fetch_bytes=fail,
        now="2026-07-30T00:00:00+00:00",
    )
    con = sqlite3.connect(db)
    evidence = con.execute(
        "SELECT fetch_status,validation_status FROM dependency_asset_evidence"
    ).fetchone()
    finding = con.execute(
        "SELECT severity FROM security_finding "
        "WHERE fingerprint='fp1' AND rule_id='dependency-fetch-failed'"
    ).fetchone()
    gate = compute_dependency_gate(con, "fp1")
    con.close()
    assert summary["jar_fetch_errors"] == 1
    assert evidence == ("failed", "fetch_error")
    assert finding == ("medium",)
    assert gate["complete"] is False


def test_review_required_jar_needs_valid_approval_and_revocation_is_immediate(tmp_path):
    payload = _jar_bytes(embedded_binary=True)
    digest = hashlib.md5(payload).hexdigest()
    sha256 = hashlib.sha256(payload).hexdigest()
    url = "https://assets.example/spider.jar"
    db, rules, allowlist, report = _seed_dependency_db(
        tmp_path, declared_md5=digest, url=url
    )
    scan_security.run_scan(
        str(db),
        str(rules),
        str(allowlist),
        str(report),
        fetch_bytes=lambda *_args, **_kwargs: payload,
        jar_only=True,
        now="2026-07-30T00:00:00+00:00",
    )
    review_time = datetime(2026, 7, 30, tzinfo=timezone.utc)
    con = sqlite3.connect(db)
    assert compute_dependency_gate(con, "fp1", now=review_time)["complete"] is False
    con.close()

    approval = approve_asset(
        str(db),
        sha256=sha256,
        repo="owner/repository",
        commit="a" * 40,
        path="jar/spider.jar",
        reviewer="jie",
        reason="已核对上游固定提交和静态扫描结果",
        days=60,
        now=review_time,
        provenance_verifier=_verified_provenance(sha256),
    )
    con = sqlite3.connect(db)
    gate = compute_dependency_gate(con, "fp1", now=review_time + timedelta(days=1))
    event_count = con.execute(
        "SELECT COUNT(*) FROM dependency_asset_approval_event WHERE content_sha256=?",
        (sha256,),
    ).fetchone()[0]
    con.close()
    assert approval["status"] == "approved"
    assert gate["complete"] is True
    assert gate["jar_approved"] == 1
    assert event_count == 1

    set_asset_decision(
        str(db),
        sha256=sha256,
        status="revoked",
        actor="jie",
        reason="上游来源发生变化，立即撤销现有授权",
        now=review_time + timedelta(days=2),
    )
    con = sqlite3.connect(db)
    revoked = compute_dependency_gate(con, "fp1", now=review_time + timedelta(days=2))
    con.close()
    assert revoked["complete"] is False
    assert revoked["approval_statuses"] == {"revoked": 1}


def test_expired_approval_and_changed_hash_cannot_pass(tmp_path):
    payload = _jar_bytes(embedded_binary=True)
    digest = hashlib.md5(payload).hexdigest()
    sha256 = hashlib.sha256(payload).hexdigest()
    url = "https://assets.example/spider.jar"
    db, rules, allowlist, report = _seed_dependency_db(
        tmp_path, declared_md5=digest, url=url
    )
    scan_security.run_scan(
        str(db),
        str(rules),
        str(allowlist),
        str(report),
        fetch_bytes=lambda *_args, **_kwargs: payload,
        jar_only=True,
        now="2026-07-30T00:00:00+00:00",
    )
    review_time = datetime(2026, 7, 30, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="Git Blob SHA-256"):
        approve_asset(
            str(db),
            sha256=sha256,
            repo="owner/repository",
            commit="b" * 40,
            path="jar/spider.jar",
            reviewer="jie",
            reason="固定提交内容不一致时必须阻止审批",
            days=1,
            now=review_time,
            provenance_verifier=_verified_provenance("f" * 64),
        )
    approve_asset(
        str(db),
        sha256=sha256,
        repo="owner/repository",
        commit="b" * 40,
        path="jar/spider.jar",
        reviewer="jie",
        reason="固定一天用于验证审批过期门禁行为",
        days=1,
        now=review_time,
        provenance_verifier=_verified_provenance(sha256),
    )
    con = sqlite3.connect(db)
    expired = compute_dependency_gate(con, "fp1", now=review_time + timedelta(days=2))
    con.execute(
        "UPDATE dependency_asset_evidence SET content_sha256=? WHERE fingerprint='fp1'",
        ("c" * 64,),
    )
    changed = compute_dependency_gate(con, "fp1", now=review_time + timedelta(hours=1))
    con.close()
    assert expired["complete"] is False
    assert expired["approval_statuses"] == {"expired": 1}
    assert changed["complete"] is False
    assert changed["approval_statuses"] == {"not_approved": 1}


def test_approval_rejects_high_findings_and_report_deduplicates(tmp_path):
    payload = _jar_bytes(embedded_binary=True)
    digest = hashlib.md5(payload).hexdigest()
    sha256 = hashlib.sha256(payload).hexdigest()
    url = "https://assets.example/spider.jar"
    db, rules, allowlist, report = _seed_dependency_db(
        tmp_path, declared_md5=digest, url=url
    )
    scan_security.run_scan(
        str(db),
        str(rules),
        str(allowlist),
        str(report),
        fetch_bytes=lambda *_args, **_kwargs: payload,
        jar_only=True,
        now="2026-07-30T00:00:00+00:00",
    )
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO security_finding"
        "(fingerprint,target_url,asset_type,rule_id,severity,evidence,scanned_at) "
        "VALUES('fp1',?,'jar','manual-high','high','test','T')",
        (url,),
    )
    con.commit()
    con.close()
    with pytest.raises(ValueError, match="高危"):
        approve_asset(
            str(db),
            sha256=sha256,
            repo="owner/repository",
            commit="d" * 40,
            path="jar/spider.jar",
            reviewer="jie",
            reason="该记录仅用于验证高危审批阻断",
            days=30,
            now=datetime(2026, 7, 30, tzinfo=timezone.utc),
            provenance_verifier=_verified_provenance(sha256),
        )
    rejected = set_asset_decision(
        str(db),
        sha256=sha256,
        status="rejected",
        actor="jie",
        reason="存在高危静态发现，因此明确拒绝该文件",
        repo="owner/repository",
        commit="d" * 40,
        now=datetime(2026, 7, 30, tzinfo=timezone.utc),
    )
    review = build_review_report(
        str(db), now=datetime(2026, 7, 30, tzinfo=timezone.utc)
    )
    assert rejected["status"] == "rejected"
    assert len(review["assets"]) == 1
    assert review["assets"][0]["content_sha256"] == sha256
    assert review["assets"][0]["approval_status"] == "rejected"
