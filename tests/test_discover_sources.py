#!/usr/bin/env python3
import json
import sqlite3
import pytest
from ponyo_source_manager.discovery.discover_sources import (
    discover_and_import,
    fetch_subscription_config,
    load_discovery_entries,
)
from ponyo_source_manager.core.initdb import init_db


def test_fetch_subscription_config_mock():
    def mock_fetch(url, timeout=10.0):
        return """{
            // 这是注释
            "sites": [
                {"key": "test1", "name": "测试源1", "type": 3, "api": "http://api.test/vod"}
            ]
        }"""

    data, etag, content_hash = fetch_subscription_config("http://example.com/sub.json", fetch_fn=mock_fetch)
    assert data is not None
    assert len(data["sites"]) == 1



def test_discover_and_import(tmp_path, policy):
    db_path = tmp_path / "test.db"
    init_db(str(db_path))

    policy_file = tmp_path / "policy.json"
    policy_file.write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")

    def mock_fetch(url, timeout=10.0):
        return json.dumps({
            "sites": [
                {"key": "new1", "name": "新动漫源", "type": 3, "api": "http://anime.test/api"},
                {"key": "new2", "name": "新影视源", "type": 3, "api": "http://movie.test/api"}
            ]
        })

    res = discover_and_import(
        str(db_path),
        ["http://example.com/sub.json"],
        str(policy_file),
        "test-batch",
        fetch_fn=mock_fetch
    )

    assert res["urls_successful"] == 1
    assert res["raw_sites_found"] == 2
    assert res["new_candidates_added"] == 2

    # 再次导入相同的，测试去重
    res2 = discover_and_import(
        str(db_path),
        ["http://example.com/sub.json"],
        str(policy_file),
        "test-batch-2",
        fetch_fn=mock_fetch
    )
    assert res2["duplicates_skipped"] == 2
    assert res2["new_candidates_added"] == 0


def test_load_discovery_entries_expands_repositories_and_deduplicates(tmp_path):
    (tmp_path / "watch-subscriptions.json").write_text(json.dumps([
        {"url": "https://example.com/a.json", "enabled": True},
        {"url": "https://example.com/disabled.json", "enabled": False},
    ]), encoding="utf-8")
    (tmp_path / "manual-seeds.json").write_text(json.dumps([
        {"url": "https://example.com/a.json", "enabled": True},
    ]), encoding="utf-8")
    (tmp_path / "watch-repos.json").write_text(json.dumps([
        {
            "provider": "github", "repo": "owner/project", "branch": "main",
            "paths": ["box.json", "nested/config.json"], "enabled": True,
        },
        {
            "provider": "jsdelivr", "repo": "mirror/project", "branch": "main",
            "paths": ["box.json"], "enabled": True,
        },
        {
            "provider": "gitee", "repo": "owner/project", "branch": "master",
            "paths": ["tvbox.json"], "enabled": True,
        },
    ]), encoding="utf-8")

    entries = load_discovery_entries(tmp_path)
    assert len(entries) == 5
    urls = {entry["url"] for entry in entries}
    assert "https://raw.githubusercontent.com/owner/project/main/box.json" in urls
    assert "https://cdn.jsdelivr.net/gh/mirror/project@main/box.json" in urls
    assert "https://gitee.com/owner/project/raw/master/tvbox.json" in urls
    subscription = next(e for e in entries if e["url"] == "https://example.com/a.json")
    assert subscription["configured_by"] == [
        "watch-subscriptions.json", "manual-seeds.json"
    ]


def test_load_discovery_entries_rejects_invalid_repository(tmp_path):
    (tmp_path / "watch-subscriptions.json").write_text("[]", encoding="utf-8")
    (tmp_path / "manual-seeds.json").write_text("[]", encoding="utf-8")
    (tmp_path / "watch-repos.json").write_text(json.dumps([
        {"provider": "unknown", "repo": "owner/project", "paths": ["x.json"]}
    ]), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported provider"):
        load_discovery_entries(tmp_path)
