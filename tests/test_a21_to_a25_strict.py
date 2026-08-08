#!/usr/bin/env python3
"""A21 - A25 硬性验收标准自动化测试套件"""
import json
import sqlite3
import pytest
from pathlib import Path
from ponyo_source_manager.core.initdb import init_db
from ponyo_source_manager.scoring.dedupe import run_dedupe
from ponyo_source_manager.probes.scan_security import sanitize_evidence
from ponyo_source_manager.discovery.discover_sources import discover_and_import

SOURCE_MANAGER_DIR = Path(__file__).resolve().parents[1]
PONYO_ROOT = SOURCE_MANAGER_DIR.parent
POLICY_PATH = SOURCE_MANAGER_DIR / "config" / "policy.json"


@pytest.fixture(autouse=True)
def mock_dns_for_test(monkeypatch):
    from ponyo_source_manager.core import net
    orig_getaddrinfo = net._getaddrinfo
    def mock_resolver(host, timeout):
        if "invalid" in host or "example" in host:
            return True
        return orig_getaddrinfo(host, timeout)
    monkeypatch.setattr(net, "_getaddrinfo", mock_resolver)


def test_A21_primary_switch_audit_log(tmp_path):
    """A21: 主记录切换必须向 audit_log 写入审计日志。"""
    db = tmp_path / "a21.db"
    init_db(str(db))

    con = sqlite3.connect(str(db))
    # 模拟两个同指纹 raw/norm 记录
    fp = "fp_same_a21"
    con.execute("INSERT INTO raw_source (import_batch, origin, site_key, name, type, api, raw_json) VALUES ('b1', 'http://a', 'k1', 'Name1', 3, 'http://api1', '{}')")
    raw1 = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    con.execute("INSERT INTO norm_source (raw_id, fingerprint, api_host, required_urls) VALUES (?, ?, 'host1', '[]')", (raw1, fp))

    con.execute("INSERT INTO raw_source (import_batch, origin, site_key, name, type, api, raw_json) VALUES ('b1', 'http://b', 'k2', 'Name2', 3, 'http://api2', '{}')")
    raw2 = con.execute("SELECT last_insert_rowid()").fetchone()[0]

    con.execute("INSERT INTO norm_source (raw_id, fingerprint, api_host, required_urls) VALUES (?, ?, 'host2', '[]')", (raw2, fp))

    # 首次 health 标记 raw1 优于 raw2
    con.execute("INSERT INTO health_snapshot (site_key, verdict, captured_at) VALUES ('k1', 'verified', '2026-07-25T12:00:00Z'), ('k2', 'partial', '2026-07-25T12:00:00Z')")
    con.commit(); con.close()


    # 第一次 dedupe
    rep_path = tmp_path / "dedupe-rep.json"
    run_dedupe(str(db), str(POLICY_PATH), str(rep_path))

    con = sqlite3.connect(str(db))
    p1 = con.execute("SELECT primary_raw_id FROM dedup_group WHERE fingerprint=?", (fp,)).fetchone()[0]
    assert p1 == raw1

    # 切换 health verdict，使 raw2 优先于 raw1
    con.execute("UPDATE health_snapshot SET verdict='partial' WHERE site_key='k1'")
    con.execute("UPDATE health_snapshot SET verdict='verified' WHERE site_key='k2'")
    con.commit(); con.close()

    # 第二次 dedupe (触发主源切换)
    run_dedupe(str(db), str(POLICY_PATH), str(rep_path))

    con = sqlite3.connect(str(db))
    p2 = con.execute("SELECT primary_raw_id FROM dedup_group WHERE fingerprint=?", (fp,)).fetchone()[0]
    assert p2 == raw2

    # 验证 audit_log 是否写入了审计日志
    logs = con.execute("SELECT action, old_value, new_value FROM audit_log WHERE entity_id=?", (fp,)).fetchall()
    con.close()

    assert len(logs) == 1
    assert logs[0][0] == "primary_switch"
    assert logs[0][1] == str(raw1)
    assert logs[0][2] == str(raw2)


def test_A22_manual_seed_and_privacy(tmp_path):
    """A22: 人工种子提交只入 candidate 池，不得跳过验证。"""
    db = tmp_path / "a22.db"
    init_db(str(db))

    def mock_fetch(url, timeout=10.0):
        return json.dumps({"sites": [{"key": "seed_k", "name": "Seed Site", "api": "http://seed.invalid/api"}]})

    discover_and_import(str(db), ["http://seed.invalid/cfg.json"], str(POLICY_PATH), "seed_batch", fetch_fn=mock_fetch)

    con = sqlite3.connect(str(db))
    states = con.execute("SELECT state FROM list_state").fetchall()
    con.close()

    assert len(states) == 1
    assert states[0][0] == "candidate"


def test_A24_token_desensitization():
    """A24: 密码、Token、Authorization 等敏感信息必须在证据和日志中屏蔽脱敏。"""
    raw_log = "Error accessing http://site.com/api?token=secret123456 Authorization: Basic user_pass_secret"
    sanitized = sanitize_evidence(raw_log, 0, len(raw_log))
    assert "secret123456" not in sanitized
    assert "user_pass_secret" not in sanitized
    assert "****" in sanitized


def test_A25_discovery_report_metrics_align_db(tmp_path):
    """A25: 报告中统计项与数据库内部记录 100% 精确核对。"""
    db = tmp_path / "a25.db"
    init_db(str(db))

    site_data = {
        "sites": [
            {"key": "k1", "name": "Source 1", "api": "http://s1.invalid/api"},
            {"key": "k2", "name": "Source 2", "api": "http://s2.invalid/api"}
        ]
    }

    def mock_fetch(url, timeout=10.0):
        return json.dumps(site_data)

    rep = tmp_path / "disc-report.json"
    res = discover_and_import(str(db), ["http://disc.invalid/u.json"], str(POLICY_PATH), "b_a25", report_path=str(rep), fetch_fn=mock_fetch)

    con = sqlite3.connect(str(db))
    db_candidate_cnt = con.execute("SELECT count(*) FROM list_state WHERE state='candidate'").fetchone()[0]
    con.close()

    assert res["new_candidates_added"] == db_candidate_cnt
    assert res["new_candidates_added"] == 2
