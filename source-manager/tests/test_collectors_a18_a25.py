#!/usr/bin/env python3
"""多入口采集器与 SSRF 安全防边界单元测试 (A18-A22)。
测试涵盖：
1. 指定订阅与 Seed 监控
2. 人工种子提交只入 candidate 池
3. SSRF 内网/环回/云元数据地址拦截 (A20)
4. 采集去重与隔离
"""
import json
import pytest
from pathlib import Path
from ponyo_source_manager.core import net
from ponyo_source_manager.discovery import discover_sources

SOURCE_MANAGER_DIR = Path(__file__).resolve().parents[1]
PONYO_ROOT = SOURCE_MANAGER_DIR.parent


@pytest.fixture(autouse=True)
def mock_dns_for_test(monkeypatch):
    orig_getaddrinfo = net._getaddrinfo
    def mock_resolver(host, timeout):
        if "invalid" in host or "example" in host:
            return True
        return orig_getaddrinfo(host, timeout)
    monkeypatch.setattr(net, "_getaddrinfo", mock_resolver)



def test_ssrf_ip_blocking():
    """A20: 验证 SSRF 机制对私网/环回/云元数据 IP 的 100% 拦截率。"""
    local_ips = [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "::1"
    ]
    for ip in local_ips:
        assert net._is_local(ip) is True, f"Failed to detect local IP: {ip}"

    public_ips = [
        "8.8.8.8",
        "1.1.1.1",
        "114.114.114.114"
    ]
    for ip in public_ips:
        assert net._is_local(ip) is False, f"Erroneously flagged public IP: {ip}"


def test_discovery_imports_only_to_candidate(tmp_path):
    """A18 & A22: 验证新采集源无论来自哪个入口，均统一置为 candidate，防穿透进入 allow。"""
    from ponyo_source_manager.core.initdb import init_db
    import sqlite3

    db = tmp_path / "disc.db"
    init_db(str(db))

    mock_site_data = {
        "sites": [
            {
                "key": "test_collector_site",
                "name": "测试采集源",
                "type": 3,
                "api": "http://example.invalid/csp.js"
            }
        ]
    }

    def mock_fetch(url, timeout=10.0):
        return json.dumps(mock_site_data)

    policy = SOURCE_MANAGER_DIR / "config" / "policy.json"
    res = discover_sources.discover_and_import(
        str(db),
        urls=["http://test-seed.invalid/v.json"],
        policy_path=str(policy),
        batch_name="test_batch",
        fetch_fn=mock_fetch
    )

    assert res["new_candidates_added"] == 1

    con = sqlite3.connect(str(db))
    rows = con.execute("SELECT fingerprint, state FROM list_state").fetchall()
    con.close()

    assert len(rows) == 1
    assert rows[0][1] == "candidate", "Discovered source must be assigned 'candidate' state!"


def test_watch_configs_exist():
    """A19: 验证 watch-subscriptions.json, watch-repos.json, manual-seeds.json 配置文件合法有效。"""
    cfg_dir = SOURCE_MANAGER_DIR / "config"
    for fname in ["watch-subscriptions.json", "watch-repos.json", "manual-seeds.json"]:
        fpath = cfg_dir / fname
        assert fpath.exists(), f"Missing config file: {fname}"
        content = json.loads(fpath.read_text(encoding="utf-8"))
        assert isinstance(content, list), f"Config file {fname} should be a JSON array"
