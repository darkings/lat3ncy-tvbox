from ponyo_source_manager.core.initdb import init_db
from ponyo_source_manager.discovery.profile_search_collector import ProfileSearchCollector


def repository(full_name: str) -> dict:
    return {
        "full_name": full_name,
        "default_branch": "main",
        "description": "TVBox source repository",
        "pushed_at": "2026-07-29T00:00:00Z",
        "stargazers_count": 1,
    }


def settings(repo_budget: int) -> dict:
    return {
        "max_queries_per_run": 1,
        "repositories_per_query": 3,
        "max_repositories_per_run": repo_budget,
        "queries": [
            {"profile": "general", "target_lane": "general", "query": "TVBox"}
        ],
    }


class RecordingCollector:
    def __init__(self, failing_repo: str = "") -> None:
        self.calls: list[tuple[str, str]] = []
        self.failing_repo = failing_repo

    def collect_repo(self, repo: str, branch: str) -> dict:
        self.calls.append((repo, branch))
        if repo == self.failing_repo:
            raise TimeoutError("repository timeout")
        return {
            "scope": f"{repo}@{branch}",
            "status": "success",
            "downloaded": 0,
            "errors": [],
            "artifacts": [],
        }


def make_collector(tmp_path, github: RecordingCollector) -> ProfileSearchCollector:
    db = tmp_path / "sources.db"
    init_db(db)
    repositories = [
        repository("owner/first"),
        repository("owner/second"),
        repository("owner/third"),
    ]
    return ProfileSearchCollector(
        db,
        "config/policy.json",
        search_fetch=lambda *_args: {"items": repositories},
        config_fetch=lambda *_args, **_kwargs: '{"sites": []}',
        github_collector=github,
        now=lambda: "2026-07-29T00:00:00+00:00",
    )


def test_repository_backlog_persists_hits_beyond_per_run_budget(tmp_path):
    github = RecordingCollector()
    collector = make_collector(tmp_path, github)

    collector.run(settings(2))
    collector.run(settings(2))

    assert github.calls[:2] == [("owner/first", "main"), ("owner/second", "main")]
    assert ("owner/third", "main") in github.calls[2:]


def test_failed_repository_is_retried_after_never_crawled_work(tmp_path):
    github = RecordingCollector(failing_repo="owner/first")
    collector = make_collector(tmp_path, github)

    collector.run(settings(2))
    collector.run(settings(2))

    assert github.calls == [
        ("owner/first", "main"),
        ("owner/second", "main"),
        ("owner/third", "main"),
        ("owner/first", "main"),
    ]
