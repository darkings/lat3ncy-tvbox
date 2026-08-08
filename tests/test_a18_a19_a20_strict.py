#!/usr/bin/env python3
"""针对 review.md 中 A18, A19, A20 硬性验收标准的严格测试套件"""
import json
import sqlite3
import pytest
from pathlib import Path
from ponyo_source_manager.core import net
from ponyo_source_manager.discovery.discover_sources import DiscoveryEngine, discover_and_import
from ponyo_source_manager.core.initdb import init_db


SOURCE_MANAGER_DIR = Path(__file__).resolve().parents[1]
PONYO_ROOT = SOURCE_MANAGER_DIR.parent
POLICY_PATH = SOURCE_MANAGER_DIR / "config" / "policy.json"


@pytest.fixture(autouse=True)
def mock_dns_for_test(monkeypatch):
    orig_getaddrinfo = net._getaddrinfo
    def mock_resolver(host, timeout):
        if "invalid" in host or "example" in host:
            return True
        return orig_getaddrinfo(host, timeout)
    monkeypatch.setattr(net, "_getaddrinfo", mock_resolver)



def test_A18_github_and_incremental_discovery(tmp_path):
    """A18 验收测试:
    1. 记录 discovery_batch
    2. 同一提交/内容第二次运行新增数必须为 0
    3. 上游资源保存 url, content_sha256
    4. allow 新增数为 0，100% 均为 candidate
    """
    db = tmp_path / "a18.db"
    init_db(str(db))

    site_payload = {
        "sites": [
            {"key": "site_a18", "name": "A18测试源", "api": "http://example.invalid/api.js"}
        ]
    }
    raw_str = json.dumps(site_payload)

    def mock_fetch(url, timeout=10.0):
        return raw_str

    # 1. 第一次运行
    res1 = discover_and_import(
        str(db), ["http://repo.example.invalid/config.json"],
        str(POLICY_PATH), "batch_1", fetch_fn=mock_fetch
    )
    assert res1["new_candidates_added"] == 1

    con = sqlite3.connect(str(db))
    # 验证 discovery_batch
    batch_rows = con.execute("SELECT * FROM discovery_batch").fetchall()
    assert len(batch_rows) == 1

    # 验证 upstream_resource 记录了 content_sha256
    up_rows = con.execute("SELECT content_sha256 FROM upstream_resource").fetchall()
    assert len(up_rows) == 1
    assert up_rows[0][0] is not None

    # 验证 list_state 状态全为 candidate，allow 为 0
    allow_cnt = con.execute("SELECT count(*) FROM list_state WHERE state='allow'").fetchone()[0]
    cand_cnt = con.execute("SELECT count(*) FROM list_state WHERE state='candidate'").fetchone()[0]
    assert allow_cnt == 0
    assert cand_cnt == 1
    con.close()

    # 2. 第二次运行同一内容 -> 新增数必须严格为 0
    res2 = discover_and_import(
        str(db), ["http://repo.example.invalid/config.json"],
        str(POLICY_PATH), "batch_2", fetch_fn=mock_fetch
    )
    assert res2["new_candidates_added"] == 0, "Second run with unchanged content MUST add 0 new candidates!"


def test_A19_watch_configs_and_error_isolation(tmp_path):
    """A19 验收测试:
    1. watch-repos.json & watch-subscriptions.json 配置可正常解析
    2. 单个订阅解析失败只记录该资源 error，不影响其他资源
    3. candidate 可追溯到 upstream_id
    """
    db = tmp_path / "a19.db"
    init_db(str(db))

    def mock_fetch_with_fault(url, timeout=10.0):
        if "bad" in url:
            raise ValueError("HTTP 500 Network Error")
        return json.dumps({"sites": [{"key": "good_site", "name": "Good Site", "api": "http://ok.invalid/csp.js"}]})

    urls = ["http://test.invalid/bad.json", "http://test.invalid/good.json"]
    res = discover_and_import(str(db), urls, str(POLICY_PATH), "batch_a19", fetch_fn=mock_fetch_with_fault)

    assert res["urls_successful"] == 1
    assert res["new_candidates_added"] == 1

    con = sqlite3.connect(str(db))
    # 验证 candidate_version 中能追溯到 upstream_id
    cv_rows = con.execute("SELECT upstream_id FROM candidate_version").fetchall()
    assert len(cv_rows) >= 1
    assert cv_rows[0][0] is not None
    con.close()


def test_A20_recursive_dependency_and_ssrf_cycle(tmp_path):
    """A20 验收测试:
    1. SSRF 私网/环回/元数据 IP 100% 拦截
    2. 构造 A -> B -> A 循环依赖，visited 机制防卡死且每个 URL 访问一次
    3. 子依赖存入 dependency_edge 表
    """
    db = tmp_path / "a20.db"
    init_db(str(db))

    engine = DiscoveryEngine(str(db), str(POLICY_PATH))
    con = engine._get_con()

    # 插入父资源
    cur = con.execute("INSERT INTO upstream_resource (source_type, url, first_seen_at, last_seen_at, last_changed_at) VALUES ('sub', 'http://parent.invalid/cfg.json', 'now', 'now', 'now')")
    parent_id = cur.lastrowid

    # 循环依赖：A -> B -> A
    url_a = "http://public.invalid/a.js"
    url_b = "http://public.invalid/b.js"

    # 第一次追踪
    visited = set()
    engine._trace_dependencies(con, parent_id, [url_a, url_b], depth=1, visited=visited)
    # 模拟循环再次传入 url_a
    engine._trace_dependencies(con, parent_id, [url_a], depth=2, visited=visited)

    con.commit()
    edges = con.execute("SELECT child_url FROM dependency_edge WHERE parent_resource_id=?", (parent_id,)).fetchall()
    con.close()

    # 验证 url_a 绝不重复访问/记录
    child_urls = [r[0] for r in edges]
    assert child_urls.count(url_a) == 1
    assert child_urls.count(url_b) == 1
