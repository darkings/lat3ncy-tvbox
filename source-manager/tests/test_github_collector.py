from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ponyo_source_manager.core.initdb import init_db
from ponyo_source_manager.discovery.github_collector import GitHubCollector, classify_artifact


def _state_rows(db: Path) -> list[tuple]:
    with sqlite3.connect(db) as con:
        return con.execute("SELECT * FROM list_state ORDER BY fingerprint").fetchall()


def test_classification_is_conservative():
    config = json.dumps({"sites": [{"key": "a", "api": "https://a.test/api"}]}).encode()
    assert classify_artifact("config.json", config) == "tvbox_config"
    assert classify_artifact("rule.js", "var rule = {搜索: 'x'}".encode()) == "drpy2_rule"
    assert classify_artifact("package.json", b'{"name":"not-tvbox"}') is None
    assert classify_artifact("plugin.jar", config) is None


def test_incremental_github_collection_uses_fallback_and_never_promotes(tmp_path: Path):
    db = tmp_path / "sources.db"
    init_db(str(db))
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO list_state (fingerprint, state, reason, updated_at) "
            "VALUES ('existing', 'allow', 'fixture', '2026-07-27T00:00:00Z')"
        )
    before = _state_rows(db)
    calls = {"json": 0, "bytes": 0}

    def fetch_json(url: str):
        calls["json"] += 1
        if "/commits/" in url:
            return {"sha": "a" * 40}
        return {"truncated": False, "tree": [
            {"type": "blob", "path": "tv/config.json"},
            {"type": "blob", "path": "README.md"},
        ]}

    payload = json.dumps({"sites": [{"key": "fresh", "api": "https://vod.test/api"}]}).encode()

    def fetch_bytes(url: str) -> bytes:
        calls["bytes"] += 1
        if "raw.githubusercontent.com" in url:
            raise OSError("raw route unavailable")
        return payload

    collector = GitHubCollector(
        db, fetch_json=fetch_json, fetch_bytes=fetch_bytes,
        now=lambda: "2026-07-27T01:00:00+00:00",
    )
    first = collector.collect_repo("owner/repo", "main")
    assert first["status"] == "success"
    assert first["accepted"] == 1
    assert first["artifacts"][0]["effective_url"].startswith("https://cdn.jsdelivr.net/")
    assert len(first["artifacts"][0]["content_sha256"]) == 64
    assert _state_rows(db) == before

    # Same commit SHA is a hard incremental stop: no tree or content requests.
    second = collector.collect_repo("owner/repo", "main")
    assert second["status"] == "unchanged"
    assert calls == {"json": 3, "bytes": 2}
    assert _state_rows(db) == before

    with sqlite3.connect(db) as con:
        artifact = con.execute(
            "SELECT artifact_kind, effective_url, revision, content_sha256 "
            "FROM discovered_artifact"
        ).fetchone()
    assert artifact[0] == "tvbox_config"
    assert "cdn.jsdelivr.net" in artifact[1]
    assert artifact[2] == "a" * 40
    assert artifact[3] == first["artifacts"][0]["content_sha256"]


def test_repository_budget_failure_is_isolated_and_audited(tmp_path: Path):
    db = tmp_path / "sources.db"
    init_db(str(db))

    def fetch_json(url: str):
        if "/commits/" in url:
            return {"sha": "b" * 40}
        return {"truncated": True, "tree": []}

    result = GitHubCollector(db, fetch_json=fetch_json, max_tree_entries=1).collect_repo(
        "owner/large", "main"
    )
    assert result["status"] == "failed"
    assert "safety budget" in result["errors"][0]["error"]
    with sqlite3.connect(db) as con:
        cursor = con.execute(
            "SELECT revision, last_error FROM discovery_cursor WHERE scope='owner/large@main'"
        ).fetchone()
    # Failed revisions are audited but never advanced, so the next run retries.
    assert cursor[0] is None
    assert "safety budget" in cursor[1]


def test_candidate_file_budget_resumes_until_revision_is_complete(tmp_path: Path):
    db = tmp_path / "sources.db"
    init_db(str(db))
    downloads: list[str] = []

    def fetch_json(url: str):
        if "/commits/" in url:
            return {"sha": "c" * 40}
        return {"truncated": False, "tree": [
            {"type": "blob", "path": "a.json"},
            {"type": "blob", "path": "b.json"},
        ]}

    collector = GitHubCollector(
        db, fetch_json=fetch_json,
        fetch_bytes=lambda url: downloads.append(url) or b"{}",
        max_candidate_files=1,
    )
    first = collector.collect_repo("owner/noisy", "main")
    assert first["status"] == "continuing"
    assert first["candidate_total"] == 2
    assert first["batch_start"] == 0 and first["batch_end"] == 1
    assert len(downloads) == 1
    with sqlite3.connect(db) as con:
        cursor = con.execute(
            "SELECT revision, pending_revision, position FROM discovery_cursor"
        ).fetchone()
    assert cursor == (None, "c" * 40, 1)

    second = collector.collect_repo("owner/noisy", "main")
    assert second["status"] == "success"
    assert second["batch_start"] == 1 and second["batch_end"] == 2
    assert len(downloads) == 2
    with sqlite3.connect(db) as con:
        cursor = con.execute(
            "SELECT revision, pending_revision, position FROM discovery_cursor"
        ).fetchone()
    assert cursor == ("c" * 40, None, 0)


def test_failed_file_is_audited_but_does_not_starve_later_batches(tmp_path: Path):
    db = tmp_path / "sources.db"
    init_db(str(db))

    def fetch_json(url: str):
        if "/commits/" in url:
            return {"sha": "d" * 40}
        return {"truncated": False, "tree": [
            {"type": "blob", "path": "a.json"},
            {"type": "blob", "path": "b.json"},
        ]}

    def fetch_bytes(url: str) -> bytes:
        if url.endswith("/a.json"):
            raise OSError("both routes unavailable")
        return json.dumps({"sites": []}).encode()

    collector = GitHubCollector(
        db, fetch_json=fetch_json, fetch_bytes=fetch_bytes, max_candidate_files=1
    )
    first = collector.collect_repo("owner/retry", "main")
    assert first["status"] == "continuing"
    assert first["batch_end"] == 1
    assert len(first["errors"]) == 1
    with sqlite3.connect(db) as con:
        assert con.execute(
            "SELECT pending_revision, position, last_error FROM discovery_cursor"
        ).fetchone() == ("d" * 40, 1, "1 artifact download(s) failed")

    second = collector.collect_repo("owner/retry", "main")
    assert second["status"] == "success"
    assert second["batch_start"] == 1
