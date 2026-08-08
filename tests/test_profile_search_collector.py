from __future__ import annotations

import json
import sqlite3

import pytest

from ponyo_source_manager import scheduler
from ponyo_source_manager.core.initdb import init_db
from ponyo_source_manager.discovery.profile_search_collector import (
    ProfileSearchCollector,
    load_profiles,
)


class FakeGitHubCollector:
    def __init__(self):
        self.calls = []

    def collect_repo(self, repo, branch):
        self.calls.append((repo, branch))
        return {
            "scope": f"{repo}@{branch}",
            "status": "success",
            "downloaded": 1,
            "errors": [],
            "artifacts": [
                {
                    "repo": repo,
                    "branch": branch,
                    "path": "config.json",
                    "revision": "abc123",
                    "artifact_url": f"https://raw.githubusercontent.com/{repo}/{branch}/config.json",
                    "effective_url": f"https://cdn.jsdelivr.net/gh/{repo}@abc123/config.json",
                    "artifact_kind": "tvbox_config",
                    "content_sha256": "f" * 64,
                    "size": 100,
                }
            ],
        }


class FirstRepositoryFails(FakeGitHubCollector):
    def collect_repo(self, repo, branch):
        if repo == "owner/broken":
            self.calls.append((repo, branch))
            raise TimeoutError("repository timeout")
        return super().collect_repo(repo, branch)


def repository(full_name="owner/tvbox-kids"):
    return {
        "full_name": full_name,
        "default_branch": "main",
        "description": "TVBox children rules",
        "pushed_at": "2026-07-29T00:00:00Z",
        "stargazers_count": 10,
        "archived": False,
        "disabled": False,
        "fork": False,
    }


def settings(queries, *, query_budget=3, repo_budget=3):
    return {
        "max_queries_per_run": query_budget,
        "repositories_per_query": 3,
        "max_repositories_per_run": repo_budget,
        "queries": queries,
    }


def test_profile_config_validation_and_limits(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text(
        json.dumps(
            {
                "max_queries_per_run": 2,
                "repositories_per_query": 3,
                "max_repositories_per_run": 1,
                "profiles": {
                    "children": {
                        "target_lane": "children",
                        "queries": ["TVBox 儿童", "TVBox 少儿"],
                    },
                    "disabled": {"enabled": False, "queries": ["ignored"]},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    loaded = load_profiles(path)
    assert loaded["max_queries_per_run"] == 2
    assert [item["query"] for item in loaded["queries"]] == [
        "TVBox 儿童",
        "TVBox 少儿",
    ]

    path.write_text(
        json.dumps(
            {
                "max_queries_per_run": 11,
                "profiles": {"x": {"queries": ["TVBox"]}},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="max_queries_per_run"):
        load_profiles(path)


def test_discovered_config_enters_existing_candidate_pool_with_provenance(tmp_path):
    db = tmp_path / "sources.db"
    init_db(db)
    github = FakeGitHubCollector()
    search_calls = []

    def fake_search(query, page, per_page):
        search_calls.append((query, page, per_page))
        invalid = repository("owner/forked")
        invalid["fork"] = True
        return {
            "items": [repository(), invalid],
            "incomplete_results": False,
        }

    config = json.dumps(
        {
            "sites": [
                {
                    "key": "kids_candidate",
                    "name": "儿童候选",
                    "type": 3,
                    "api": "csp_TestKids",
                }
            ],
        },
        ensure_ascii=False,
    )

    collector = ProfileSearchCollector(
        db,
        "config/policy.json",
        search_fetch=fake_search,
        config_fetch=lambda *_args, **_kwargs: config,
        github_collector=github,
        now=lambda: "2026-07-29T00:00:00+00:00",
    )
    report = collector.run(
        settings(
            [
                {
                    "profile": "children",
                    "target_lane": "children",
                    "query": "TVBox 儿童",
                }
            ],
            query_budget=1,
            repo_budget=1,
        )
    )

    assert search_calls == [("TVBox 儿童", 1, 3)]
    assert github.calls == [("owner/tvbox-kids", "main")]
    assert report["summary"]["repository_hits"] == 1
    assert report["summary"]["tvbox_configs_imported"] == 1
    assert report["summary"]["sites_found"] == 1
    assert report["summary"]["candidates_added"] == 1

    with sqlite3.connect(db) as con:
        raw = con.execute("SELECT origin,site_key,name FROM raw_source").fetchone()
        state = con.execute("SELECT state FROM list_state").fetchone()
        artifact = con.execute(
            "SELECT scope,artifact_kind,metadata_json FROM discovered_artifact "
            "WHERE connector='profile_search'"
        ).fetchone()
        batch = con.execute(
            "SELECT connector,status,error_count FROM discovery_batch "
            "WHERE connector='profile_search'"
        ).fetchone()
    assert raw[1:] == ("kids_candidate", "儿童候选")
    assert "cdn.jsdelivr.net" in raw[0]
    assert state == ("candidate",)
    assert artifact[:2] == ("children", "github_repository")
    assert json.loads(artifact[2])["search_query"] == "TVBox 儿童"
    assert batch == ("profile_search", "success", 0)


def test_global_query_cursor_rotates_profiles_fairly(tmp_path):
    db = tmp_path / "sources.db"
    init_db(db)
    calls = []

    def empty_search(query, page, per_page):
        calls.append((query, page, per_page))
        return {"items": [], "incomplete_results": False}

    collector = ProfileSearchCollector(
        db,
        "config/policy.json",
        search_fetch=empty_search,
        github_collector=FakeGitHubCollector(),
    )
    configured = settings(
        [
            {"profile": "children", "target_lane": "children", "query": "儿童"},
            {"profile": "general", "target_lane": "general", "query": "影视"},
        ],
        query_budget=1,
    )
    collector.run(configured)
    collector.run(configured)

    assert [item[0] for item in calls] == ["儿童", "影视"]
    with sqlite3.connect(db) as con:
        position = con.execute(
            "SELECT position FROM discovery_cursor "
            "WHERE connector='profile_search' AND scope='global'"
        ).fetchone()[0]
    assert position == 0


def test_repository_failure_does_not_block_remaining_entries(tmp_path):
    db = tmp_path / "sources.db"
    init_db(db)
    github = FirstRepositoryFails()

    def fake_search(_query, _page, _per_page):
        return {
            "items": [repository("owner/broken"), repository("owner/working")],
            "incomplete_results": False,
        }

    config = json.dumps(
        {
            "sites": [
                {
                    "key": "working",
                    "name": "可用候选",
                    "type": 3,
                    "api": "csp_Working",
                }
            ],
        },
        ensure_ascii=False,
    )
    collector = ProfileSearchCollector(
        db,
        "config/policy.json",
        search_fetch=fake_search,
        config_fetch=lambda *_args, **_kwargs: config,
        github_collector=github,
    )
    report = collector.run(
        settings(
            [
                {
                    "profile": "general",
                    "target_lane": "general",
                    "query": "TVBox 影视",
                }
            ],
            query_budget=1,
            repo_budget=2,
        )
    )

    assert github.calls == [
        ("owner/broken", "main"),
        ("owner/working", "main"),
    ]
    assert report["summary"]["repositories_crawled"] == 2
    assert report["summary"]["tvbox_configs_imported"] == 1
    assert report["summary"]["candidates_added"] == 1
    assert report["summary"]["errors"] == 1
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT count(*) FROM raw_source").fetchone()[0] == 1
        assert con.execute(
            "SELECT status FROM discovery_batch WHERE connector='profile_search'"
        ).fetchone() == ("partial",)


def test_repository_keeps_all_search_query_provenance(tmp_path):
    db = tmp_path / "sources.db"
    init_db(db)
    collector = ProfileSearchCollector(
        db,
        "config/policy.json",
        github_collector=FakeGitHubCollector(),
        now=lambda: "2026-07-29T00:00:00+00:00",
    )
    item = repository()
    collector._save_repository("children", "children", "TVBox 儿童", item)
    collector._save_repository("children", "children", "TVBox 少儿", item)

    with sqlite3.connect(db) as con:
        metadata = json.loads(
            con.execute(
                "SELECT metadata_json FROM discovered_artifact "
                "WHERE connector='profile_search'"
            ).fetchone()[0]
        )
    assert metadata["search_queries"] == ["TVBox 儿童", "TVBox 少儿"]


def test_scheduler_runs_profile_search_before_fixed_collectors(monkeypatch, tmp_path):
    names = []

    def fake_run(_args, name, **kwargs):
        names.append(name)
        return {"returncode": 0, "output": ""}

    monkeypatch.setattr(scheduler, "_run_subprocess", fake_run)
    scheduler._run_discovery_pipeline(str(tmp_path / "sources.db"))

    assert names[:5] == [
        "profile_search_collector",
        "github_collector",
        "drpy_connector",
        "discover",
        "maccms_collector",
    ]
    assert names.index("dedupe") < names.index("maccms_media")
