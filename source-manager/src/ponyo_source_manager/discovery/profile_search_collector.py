#!/usr/bin/env python3
"""Profile-driven GitHub repository discovery feeding the existing candidate pool."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

from ponyo_source_manager.core import net
from ponyo_source_manager.core.common import CONFIG_DIR, DATA_DIR, REPORT_DIR
from ponyo_source_manager.discovery.discover_sources import DiscoveryEngine
from ponyo_source_manager.discovery.github_collector import (
    GITHUB_API,
    GitHubCollector,
    _headers,
)


DEFAULT_MAX_QUERIES = 3
DEFAULT_REPOSITORIES_PER_QUERY = 3
DEFAULT_MAX_REPOSITORIES = 3
MAX_SEARCH_PAGES = 10
MAX_CONFIGS_PER_REPOSITORY = 10
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_repository_search(query: str, page: int, per_page: int) -> dict[str, Any]:
    params = urlencode({
        "q": query,
        "sort": "updated",
        "order": "desc",
        "page": page,
        "per_page": per_page,
    })
    url = f"{GITHUB_API}/search/repositories?{params}"
    request = net.Request(url, headers=_headers())
    response = net._ssrf_opener.open(request, timeout=15.0)
    try:
        payload = net._read_and_decompress(response, 2_097_152).decode(
            "utf-8", errors="replace"
        )
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset_at = response.headers.get("X-RateLimit-Reset")
    finally:
        response.close()
    value = json.loads(payload)
    if not isinstance(value, dict) or not isinstance(value.get("items"), list):
        raise ValueError("GitHub repository search returned an invalid response")
    value["_rate_limit_remaining"] = int(remaining) if remaining else None
    value["_rate_limit_reset"] = reset_at
    return value


def load_profiles(path: str | Path) -> dict[str, Any]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("profiles"), dict):
        raise ValueError("discovery profiles must contain a profiles object")

    settings = {
        "max_queries_per_run": int(
            document.get("max_queries_per_run", DEFAULT_MAX_QUERIES)
        ),
        "repositories_per_query": int(
            document.get("repositories_per_query", DEFAULT_REPOSITORIES_PER_QUERY)
        ),
        "max_repositories_per_run": int(
            document.get("max_repositories_per_run", DEFAULT_MAX_REPOSITORIES)
        ),
        "queries": [],
    }
    if not 1 <= settings["max_queries_per_run"] <= 10:
        raise ValueError("max_queries_per_run must be between 1 and 10")
    if not 1 <= settings["repositories_per_query"] <= 10:
        raise ValueError("repositories_per_query must be between 1 and 10")
    if not 1 <= settings["max_repositories_per_run"] <= 10:
        raise ValueError("max_repositories_per_run must be between 1 and 10")

    seen: set[tuple[str, str]] = set()
    for profile, raw in document["profiles"].items():
        if not isinstance(raw, dict) or raw.get("enabled", True) is False:
            continue
        target_lane = str(raw.get("target_lane", profile)).strip()
        queries = raw.get("queries")
        if not target_lane or not isinstance(queries, list) or not queries:
            raise ValueError(f"profile {profile} requires target_lane and queries")
        for query in queries:
            normalized = " ".join(str(query).split())
            if not normalized:
                raise ValueError(f"profile {profile} contains an empty query")
            key = (str(profile), normalized)
            if key in seen:
                raise ValueError(f"duplicate discovery query: {profile}/{normalized}")
            seen.add(key)
            settings["queries"].append({
                "profile": str(profile),
                "target_lane": target_lane,
                "query": normalized,
            })
    if not settings["queries"]:
        raise ValueError("at least one enabled discovery query is required")
    return settings


class ProfileSearchCollector:
    def __init__(
        self,
        db_path: str | Path,
        policy_path: str | Path,
        *,
        search_fetch: Callable[[str, int, int], dict[str, Any]] = fetch_repository_search,
        config_fetch: Callable[..., str] | None = None,
        github_collector: GitHubCollector | None = None,
        discovery_engine: DiscoveryEngine | None = None,
        now: Callable[[], str] = _now,
    ) -> None:
        self.db_path = Path(db_path)
        self.policy_path = Path(policy_path)
        self.search_fetch = search_fetch
        self.config_fetch = config_fetch
        self.github = github_collector or GitHubCollector(self.db_path)
        self.engine = discovery_engine or DiscoveryEngine(
            str(self.db_path), str(self.policy_path)
        )
        self.now = now

    def _cursor_position(self, scope: str, default: int) -> int:
        with sqlite3.connect(self.db_path) as con:
            row = con.execute(
                "SELECT position FROM discovery_cursor "
                "WHERE connector='profile_search' AND scope=?",
                (scope,),
            ).fetchone()
        return int(row[0]) if row else default

    def _save_cursor(self, scope: str, position: int, error: str | None = None) -> None:
        timestamp = self.now()
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT INTO discovery_cursor"
                "(connector,scope,position,checked_at,last_error) "
                "VALUES('profile_search',?,?,?,?) "
                "ON CONFLICT(connector,scope) DO UPDATE SET "
                "position=excluded.position,checked_at=excluded.checked_at,"
                "last_error=excluded.last_error",
                (scope, position, timestamp, error),
            )

    def _save_repository(
        self, profile: str, target_lane: str, query: str, item: dict[str, Any]
    ) -> None:
        full_name = str(item.get("full_name", "")).strip()
        branch = str(item.get("default_branch", "main")).strip() or "main"
        timestamp = self.now()
        artifact_url = f"https://github.com/{full_name}"
        with sqlite3.connect(self.db_path) as con:
            old = con.execute(
                "SELECT content_sha256,first_seen_at,last_changed_at,metadata_json "
                "FROM discovered_artifact WHERE connector='profile_search' "
                "AND scope=? AND artifact_url=?",
                (profile, artifact_url),
            ).fetchone()
        previous_metadata = json.loads(old[3]) if old and old[3] else {}
        search_queries = sorted(set([
            *previous_metadata.get("search_queries", []),
            previous_metadata.get("search_query", ""),
            query,
        ]) - {""})
        metadata = json.dumps({
            "profile": profile,
            "target_lane": target_lane,
            "search_query": query,
            "search_queries": search_queries,
            "repo": full_name,
            "default_branch": branch,
            "description": str(item.get("description") or "")[:500],
            "pushed_at": item.get("pushed_at"),
            "stargazers_count": int(item.get("stargazers_count") or 0),
            "last_crawled_at": previous_metadata.get("last_crawled_at"),
            "crawl_status": previous_metadata.get("crawl_status"),
            "crawl_error": previous_metadata.get("crawl_error"),
        }, ensure_ascii=False, sort_keys=True)
        content_hash = hashlib.sha256(metadata.encode("utf-8")).hexdigest()
        scope = profile
        with sqlite3.connect(self.db_path) as con:
            first_seen = old[1] if old else timestamp
            changed_at = old[2] if old and old[0] == content_hash else timestamp
            con.execute(
                "INSERT INTO discovered_artifact"
                "(connector,scope,artifact_url,effective_url,artifact_kind,revision,"
                "content_sha256,metadata_json,first_seen_at,last_seen_at,last_changed_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(connector,scope,artifact_url) DO UPDATE SET "
                "revision=excluded.revision,content_sha256=excluded.content_sha256,"
                "metadata_json=excluded.metadata_json,last_seen_at=excluded.last_seen_at,"
                "last_changed_at=excluded.last_changed_at",
                (
                    "profile_search", scope, artifact_url, artifact_url,
                    "github_repository", branch, content_hash, metadata,
                    first_seen, timestamp, changed_at,
                ),
            )

    @staticmethod
    def _repo_from_artifact_url(artifact_url: str) -> str:
        prefix = "https://github.com/"
        if not artifact_url.startswith(prefix):
            return ""
        return artifact_url.removeprefix(prefix).strip("/")

    def _repository_backlog(self, limit: int) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as con:
            rows = con.execute(
                "SELECT artifact_url,metadata_json FROM discovered_artifact "
                "WHERE connector='profile_search' "
                "AND artifact_kind='github_repository'"
            ).fetchall()
        grouped: dict[str, dict[str, Any]] = {}
        for artifact_url, metadata_json in rows:
            metadata = json.loads(metadata_json or "{}")
            repo = str(
                metadata.get("repo") or self._repo_from_artifact_url(artifact_url)
            )
            if not REPOSITORY_RE.fullmatch(repo):
                continue
            entry = grouped.setdefault(repo, {
                "repo": repo,
                "branch": str(metadata.get("default_branch") or "main"),
                "profiles": set(),
                    "last_crawled_at": metadata.get("last_crawled_at"),
                    "crawl_status": metadata.get("crawl_status"),
            })
            entry["profiles"].add(str(metadata.get("profile") or "unknown"))
            crawled = metadata.get("last_crawled_at")
            if not entry.get("last_crawled_at") or (crawled and crawled < entry["last_crawled_at"]):
                entry["last_crawled_at"] = crawled
        def queue_priority(item: dict[str, Any]) -> tuple[int, str]:
            if not item.get("last_crawled_at"):
                return (0, "")
            if item.get("crawl_status") == "failed":
                return (1, str(item.get("last_crawled_at") or ""))
            return (2, str(item.get("last_crawled_at") or ""))

        ordered = sorted(grouped.values(), key=queue_priority)
        for item in ordered:
            item["profiles"] = sorted(item["profiles"])
        return ordered[:limit]

    def _mark_repository_crawled(
        self, repo: str, status: str, error: str | None = None
    ) -> None:
        timestamp = self.now()
        artifact_url = f"https://github.com/{repo}"
        with sqlite3.connect(self.db_path) as con:
            rows = con.execute(
                "SELECT id,metadata_json FROM discovered_artifact "
                "WHERE connector='profile_search' AND artifact_url=?",
                (artifact_url,),
            ).fetchall()
            for artifact_id, metadata_json in rows:
                metadata = json.loads(metadata_json or "{}")
                metadata["last_crawled_at"] = timestamp
                metadata["crawl_status"] = status
                metadata["crawl_error"] = error
                con.execute(
                    "UPDATE discovered_artifact SET metadata_json=?,last_seen_at=? "
                    "WHERE id=?",
                    (
                        json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                        timestamp,
                        artifact_id,
                    ),
                )

    def _stored_tvbox_configs(self, repo: str, branch: str) -> list[dict[str, Any]]:
        scope = f"{repo}@{branch}"
        with sqlite3.connect(self.db_path) as con:
            rows = con.execute(
                "SELECT artifact_url,effective_url,revision,metadata_json "
                "FROM discovered_artifact WHERE connector='github' AND scope=? "
                "AND artifact_kind='tvbox_config' ORDER BY last_seen_at DESC LIMIT ?",
                (scope, MAX_CONFIGS_PER_REPOSITORY),
            ).fetchall()
        configs = []
        for artifact_url, effective_url, revision, metadata_json in rows:
            metadata = json.loads(metadata_json or "{}")
            configs.append({
                "repo": repo,
                "branch": branch,
                "path": str(metadata.get("path") or artifact_url.rsplit("/", 1)[-1]),
                "revision": revision,
                "artifact_url": artifact_url,
                "effective_url": effective_url or artifact_url,
                "artifact_kind": "tvbox_config",
            })
        return configs

    @staticmethod
    def _valid_repository(item: dict[str, Any]) -> bool:
        full_name = str(item.get("full_name", "")).strip()
        return bool(
            REPOSITORY_RE.fullmatch(full_name)
            and not item.get("archived")
            and not item.get("disabled")
            and not item.get("fork")
        )

    def run(self, settings: dict[str, Any]) -> dict[str, Any]:
        all_queries = settings["queries"]
        start = self._cursor_position("global", 0) % len(all_queries)
        count = min(settings["max_queries_per_run"], len(all_queries))
        selected = [all_queries[(start + offset) % len(all_queries)] for offset in range(count)]
        self._save_cursor("global", (start + count) % len(all_queries))

        batch_id = self.engine.start_batch(
            "profile_search", query=",".join(item["query"] for item in selected)
        )
        report: dict[str, Any] = {
            "generated_at": self.now(),
            "connector": "profile_search",
            "queries": [],
            "repositories": [],
            "imports": [],
            "errors": [],
        }
        repository_queue: dict[str, dict[str, Any]] = {}
        request_count = 0
        rate_limit_values: list[int] = []

        for selected_query in selected:
            profile = selected_query["profile"]
            query = selected_query["query"]
            scope = f"query:{profile}:{query}"
            page = max(1, self._cursor_position(scope, 1))
            query_report = {
                "profile": profile,
                "target_lane": selected_query["target_lane"],
                "query": query,
                "page": page,
                "repositories": [],
            }
            try:
                payload = self.search_fetch(
                    query, page, settings["repositories_per_query"]
                )
                request_count += 1
                items = [
                    item for item in payload.get("items", [])
                    if isinstance(item, dict) and self._valid_repository(item)
                ]
                for item in items:
                    full_name = str(item["full_name"])
                    branch = str(item.get("default_branch") or "main")
                    self._save_repository(
                        profile, selected_query["target_lane"], query, item
                    )
                    query_report["repositories"].append(full_name)
                    repository_queue.setdefault(full_name, {
                        "repo": full_name,
                        "branch": branch,
                        "profiles": [],
                    })["profiles"].append(profile)
                next_page = page + 1
                if len(payload.get("items", [])) < settings["repositories_per_query"]:
                    next_page = 1
                if next_page > MAX_SEARCH_PAGES:
                    next_page = 1
                self._save_cursor(scope, next_page)
                query_report["incomplete_results"] = bool(
                    payload.get("incomplete_results")
                )
                query_report["rate_limit_remaining"] = payload.get(
                    "_rate_limit_remaining"
                )
                query_report["rate_limit_reset"] = payload.get("_rate_limit_reset")
                if payload.get("_rate_limit_remaining") is not None:
                    rate_limit_values.append(int(payload["_rate_limit_remaining"]))
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                self._save_cursor(scope, page, message)
                query_report["error"] = message
                report["errors"].append({"scope": scope, "error": message})
            report["queries"].append(query_report)

        queued = self._repository_backlog(settings["max_repositories_per_run"])
        for repository in queued:
            try:
                crawl = self.github.collect_repo(repository["repo"], repository["branch"])
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                self._mark_repository_crawled(repository["repo"], "failed", message)
                report["errors"].append({
                    "scope": repository["repo"],
                    "error": message,
                })
                continue
            self._mark_repository_crawled(
                repository["repo"], str(crawl.get("status") or "unknown")
            )
            request_count += 2 + int(crawl.get("downloaded") or 0)
            crawl["profiles"] = sorted(set(repository["profiles"]))
            report["repositories"].append(crawl)
            report["errors"].extend(crawl.get("errors", []))
            # Real GitHubCollector persists artifacts, while injected collectors used
            # by tests or future connectors may only return them.  Merge both views
            # so an artifact is importable immediately and remains retryable later.
            current_configs = [
                artifact
                for artifact in crawl.get("artifacts", [])
                if artifact.get("artifact_kind") == "tvbox_config"
            ]
            stored_configs = self._stored_tvbox_configs(
                repository["repo"], repository["branch"]
            )
            seen_configs: set[tuple[str, str, str, str]] = set()
            for artifact in [*current_configs, *stored_configs]:
                artifact.setdefault("repo", repository["repo"])
                artifact.setdefault("branch", repository["branch"])
                artifact.setdefault(
                    "path", str(artifact.get("artifact_url", "")).rsplit("/", 1)[-1]
                )
                artifact.setdefault(
                    "effective_url", artifact.get("artifact_url", "")
                )
                config_key = (
                    str(artifact["repo"]),
                    str(artifact["branch"]),
                    str(artifact["path"]),
                    str(artifact["effective_url"]),
                )
                if config_key in seen_configs:
                    continue
                seen_configs.add(config_key)
                import_args = {
                    "connector": "profile_search",
                    "batch_id": batch_id,
                    "source_type": "github_profile_config",
                    "repo": artifact["repo"],
                    "branch": artifact["branch"],
                    "path": artifact["path"],
                }
                if self.config_fetch is not None:
                    import_args["fetch_fn"] = self.config_fetch
                try:
                    imported = self.engine.process_url_source(
                        artifact["effective_url"], **import_args
                    )
                except Exception as exc:
                    report["errors"].append({
                        "scope": f"{artifact['repo']}:{artifact['path']}",
                        "error": f"{type(exc).__name__}: {exc}",
                    })
                    continue
                report["imports"].append({
                    "repo": artifact["repo"],
                    "path": artifact["path"],
                    "profiles": sorted(set(repository["profiles"])),
                    **imported,
                })

        error_count = len(report["errors"]) + sum(
            int(item.get("errors") or 0) for item in report["imports"]
        )
        status = "partial" if error_count else "success"
        self.engine.finish_batch(
            batch_id,
            status,
            request_count,
            error_count,
            rate_limit=min(rate_limit_values) if rate_limit_values else None,
        )
        report["summary"] = {
            "queries_attempted": len(selected),
            "repository_hits": sum(
                len(item.get("repositories", [])) for item in report["queries"]
            ),
            "unique_repositories": len(repository_queue),
            "repository_backlog": len(self._repository_backlog(10_000)),
            "repositories_crawled": len(queued),
            "tvbox_configs_imported": len(report["imports"]),
            "sites_found": sum(
                int(item.get("sites_found") or 0) for item in report["imports"]
            ),
            "candidates_added": sum(
                int(item.get("added") or 0) for item in report["imports"]
            ),
            "candidates_updated": sum(
                int(item.get("updated") or 0) for item in report["imports"]
            ),
            "errors": error_count,
            "next_query_index": (start + count) % len(all_queries),
        }
        return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DATA_DIR / "sources.db"))
    parser.add_argument("--policy", default=str(CONFIG_DIR / "policy.json"))
    parser.add_argument(
        "--profiles", default=str(CONFIG_DIR / "discovery_profiles.json")
    )
    parser.add_argument(
        "--report", default=str(REPORT_DIR / "profile-discovery-report.json")
    )
    args = parser.parse_args()
    settings = load_profiles(args.profiles)
    report = ProfileSearchCollector(args.db, args.policy).run(settings)
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
