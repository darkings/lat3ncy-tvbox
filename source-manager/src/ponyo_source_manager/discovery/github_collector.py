#!/usr/bin/env python3
"""Incrementally discover TVBox-related artifacts in watched GitHub repositories.

The collector deliberately does not import sources or mutate ``list_state``.  It
stores provenance and immutable content hashes for the later audit pipeline.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote
from urllib.request import Request

from ponyo_source_manager.core import net
from ponyo_source_manager.core.common import CONFIG_DIR, DATA_DIR, REPORT_DIR

GITHUB_API = "https://api.github.com"
MAX_TREE_ENTRIES = 5_000
MAX_CANDIDATE_FILES_PER_REPO = 20
DEFAULT_DOWNLOAD_WORKERS = 10
MAX_ARTIFACT_BYTES = 2_048_576


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ponyo-source-manager/1.0",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _fetch_json(url: str, *, timeout: float = 15.0) -> dict[str, Any]:
    request = Request(url, headers=_headers())
    response = net._ssrf_opener.open(request, timeout=timeout)
    try:
        text = net._read_and_decompress(response, MAX_ARTIFACT_BYTES).decode(
            "utf-8", errors="replace"
        )
    finally:
        response.close()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object from {url}")
    return value


def _fetch_bytes(url: str, *, timeout: float = 5.0) -> bytes:
    return net.fetch_bytes(url, timeout=timeout, max_bytes=MAX_ARTIFACT_BYTES + 1)


@dataclass(frozen=True)
class Artifact:
    repo: str
    branch: str
    path: str
    revision: str
    artifact_url: str
    effective_url: str
    artifact_kind: str
    content_sha256: str
    size: int


def classify_artifact(path: str, content: bytes) -> str | None:
    """Return a conservative artifact kind, or ``None`` for irrelevant files."""
    lower_path = path.lower()
    if lower_path.endswith((".apk", ".jar", ".so", ".zip", ".7z", ".exe")):
        return None
    if len(content) > MAX_ARTIFACT_BYTES:
        return None
    text = content.decode("utf-8", errors="ignore").lstrip("\ufeff")
    if lower_path.endswith(".json"):
        try:
            parsed = json.loads("\n".join(
                line for line in text.splitlines() if not line.lstrip().startswith("//")
            ))
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, dict) and isinstance(parsed.get("sites"), list):
            return "tvbox_config"
    if lower_path.endswith((".js", ".mjs")):
        drpy_markers = ("var rule", "let rule", "const rule", "搜索:", "一级:", "二级:")
        if any(marker in text for marker in drpy_markers):
            return "drpy2_rule"
    if lower_path.endswith((".json", ".txt", ".conf")) and (
        "/api.php/provide/vod" in text or "/cjapi/" in text
    ):
        return "endpoint_list"
    return None


def _candidate_path(path: str) -> bool:
    lower = path.lower()
    if not lower.endswith((".json", ".js", ".mjs", ".txt", ".conf")):
        return False
    ignored = ("node_modules/", "vendor/", "dist/", "build/", ".github/")
    return not any(part in lower for part in ignored)


def _candidate_priority(item: dict[str, Any]) -> tuple[int, int, str]:
    path = str(item.get("path", ""))
    lower = path.lower()
    name = lower.rsplit("/", 1)[-1]
    preferred_names = {"config.json", "js.json", "tvbox.json", "index.json"}
    if name in preferred_names:
        rank = 0
    elif lower.startswith(("js/", "json/", "drpy/", "drpy2/", "config/")):
        rank = 1
    else:
        rank = 2
    return rank, lower.count("/"), lower


def _download_urls(repo: str, revision: str, path: str) -> list[str]:
    encoded_path = "/".join(quote(part, safe="") for part in path.split("/"))
    return [
        f"https://raw.githubusercontent.com/{repo}/{revision}/{encoded_path}",
        f"https://cdn.jsdelivr.net/gh/{repo}@{revision}/{encoded_path}",
    ]


def _download_with_fallback(
    urls: list[str], fetch_bytes: Callable[[str], bytes]
) -> tuple[bytes, str]:
    errors: list[str] = []
    for url in urls:
        try:
            return fetch_bytes(url), url
        except Exception as exc:  # one route must not block the fallback route
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    raise RuntimeError("; ".join(errors))


class GitHubCollector:
    def __init__(
        self,
        db_path: str | Path,
        *,
        fetch_json: Callable[[str], dict[str, Any]] = _fetch_json,
        fetch_bytes: Callable[[str], bytes] = _fetch_bytes,
        now: Callable[[], str] = _now,
        max_tree_entries: int = MAX_TREE_ENTRIES,
        max_candidate_files: int = MAX_CANDIDATE_FILES_PER_REPO,
        download_workers: int = DEFAULT_DOWNLOAD_WORKERS,
    ) -> None:
        self.db_path = Path(db_path)
        self.fetch_json = fetch_json
        self.fetch_bytes = fetch_bytes
        self.now = now
        self.max_tree_entries = max_tree_entries
        self.max_candidate_files = max_candidate_files
        self.download_workers = max(1, min(download_workers, 12))

    def _inspect_candidate(
        self, repo: str, branch: str, revision: str, item: dict[str, Any]
    ) -> tuple[str, Artifact | dict[str, str] | None]:
        path = str(item.get("path", ""))
        pinned_raw_url, fallback_url = _download_urls(repo, revision, path)
        canonical_url = _download_urls(repo, branch, path)[0]
        try:
            content, effective_url = _download_with_fallback(
                [pinned_raw_url, fallback_url], self.fetch_bytes
            )
            kind = classify_artifact(path, content)
            if kind is None:
                return "rejected", None
            return "accepted", Artifact(
                repo=repo, branch=branch, path=path, revision=revision,
                artifact_url=canonical_url, effective_url=effective_url,
                artifact_kind=kind, content_sha256=_sha256(content), size=len(content),
            )
        except Exception as exc:
            return "error", {"path": path, "error": f"{type(exc).__name__}: {exc}"}

    def _cursor(self, repo: str, branch: str) -> str | None:
        return self._cursor_state(repo, branch)[0]

    def _cursor_state(self, repo: str, branch: str) -> tuple[str | None, str | None, int]:
        with sqlite3.connect(self.db_path) as con:
            row = con.execute(
                "SELECT revision, pending_revision, position FROM discovery_cursor "
                "WHERE connector='github' AND scope=?",
                (f"{repo}@{branch}",),
            ).fetchone()
        return (row[0], row[1], int(row[2] or 0)) if row else (None, None, 0)

    def _save_cursor(
        self, repo: str, branch: str, revision: str | None,
        error: str | None = None, *, pending_revision: str | None = None,
        position: int = 0,
    ) -> None:
        timestamp = self.now()
        scope = f"{repo}@{branch}"
        with sqlite3.connect(self.db_path) as con:
            previous = con.execute(
                "SELECT revision, changed_at FROM discovery_cursor "
                "WHERE connector='github' AND scope=?",
                (scope,),
            ).fetchone()
            changed_at = timestamp if not previous or previous[0] != revision else previous[1]
            con.execute(
                "INSERT INTO discovery_cursor "
                "(connector, scope, revision, pending_revision, position, checked_at, "
                "changed_at, last_error) VALUES ('github', ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(connector, scope) DO UPDATE SET "
                "revision=excluded.revision, pending_revision=excluded.pending_revision, "
                "position=excluded.position, checked_at=excluded.checked_at, "
                "changed_at=excluded.changed_at, last_error=excluded.last_error",
                (scope, revision, pending_revision, position, timestamp, changed_at, error),
            )

    def _save_artifact(self, artifact: Artifact) -> None:
        timestamp = self.now()
        scope = f"{artifact.repo}@{artifact.branch}"
        metadata = json.dumps(
            {"repo": artifact.repo, "branch": artifact.branch, "path": artifact.path,
             "size": artifact.size},
            ensure_ascii=False,
            sort_keys=True,
        )
        with sqlite3.connect(self.db_path) as con:
            old = con.execute(
                "SELECT content_sha256, first_seen_at, last_changed_at "
                "FROM discovered_artifact WHERE connector='github' AND scope=? "
                "AND artifact_url=?",
                (scope, artifact.artifact_url),
            ).fetchone()
            first_seen = old[1] if old else timestamp
            changed_at = old[2] if old and old[0] == artifact.content_sha256 else timestamp
            con.execute(
                "INSERT INTO discovered_artifact "
                "(connector, scope, artifact_url, effective_url, artifact_kind, revision, "
                "content_sha256, metadata_json, first_seen_at, last_seen_at, last_changed_at) "
                "VALUES ('github', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(connector, scope, artifact_url) DO UPDATE SET "
                "effective_url=excluded.effective_url, artifact_kind=excluded.artifact_kind, "
                "revision=excluded.revision, content_sha256=excluded.content_sha256, "
                "metadata_json=excluded.metadata_json, last_seen_at=excluded.last_seen_at, "
                "last_changed_at=excluded.last_changed_at",
                (scope, artifact.artifact_url, artifact.effective_url,
                 artifact.artifact_kind, artifact.revision, artifact.content_sha256,
                 metadata, first_seen, timestamp, changed_at),
            )

    def collect_repo(self, repo: str, branch: str = "main") -> dict[str, Any]:
        scope = f"{repo}@{branch}"
        report: dict[str, Any] = {
            "scope": scope, "status": "failed", "revision": None,
            "head_revision": None,
            "unchanged": False, "tree_entries": 0, "downloaded": 0,
            "candidate_total": 0, "batch_start": 0, "batch_end": 0,
            "accepted": 0, "rejected": 0, "errors": [], "artifacts": [],
        }
        try:
            completed_revision, pending_revision, position = self._cursor_state(repo, branch)
            commit = self.fetch_json(f"{GITHUB_API}/repos/{repo}/commits/{quote(branch, safe='')}")
            head_revision = str(commit.get("sha", "")).strip()
            if len(head_revision) < 7:
                raise ValueError("GitHub commit response has no valid sha")
            # Finish a partially processed immutable tree before moving to a newer
            # branch head; otherwise frequently updated repositories can starve.
            revision = pending_revision or head_revision
            report["head_revision"] = head_revision
            report["revision"] = revision
            if pending_revision is None and completed_revision == head_revision:
                report.update(status="unchanged", unchanged=True)
                self._save_cursor(repo, branch, head_revision)
                return report

            tree = self.fetch_json(f"{GITHUB_API}/repos/{repo}/git/trees/{revision}?recursive=1")
            entries = tree.get("tree")
            if not isinstance(entries, list):
                raise ValueError("GitHub tree response has no tree array")
            if tree.get("truncated") or len(entries) > self.max_tree_entries:
                raise ValueError("repository tree exceeds the configured safety budget")
            report["tree_entries"] = len(entries)

            candidates = [
                item for item in entries
                if isinstance(item, dict) and item.get("type") == "blob"
                and _candidate_path(str(item.get("path", "")))
                and int(item.get("size") or 0) <= MAX_ARTIFACT_BYTES
            ]
            candidates.sort(key=_candidate_priority)
            start = position if pending_revision == revision else 0
            end = min(start + self.max_candidate_files, len(candidates))
            report.update(candidate_total=len(candidates), batch_start=start, batch_end=end)

            selected = candidates[start:end]
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.download_workers
            ) as executor:
                outcomes = executor.map(
                    lambda item: self._inspect_candidate(repo, branch, revision, item),
                    selected,
                )
                for outcome, evidence in outcomes:
                    if outcome == "error":
                        report["errors"].append(evidence)
                        continue
                    report["downloaded"] += 1
                    if outcome == "rejected":
                        report["rejected"] += 1
                        continue
                    artifact = evidence
                    assert isinstance(artifact, Artifact)
                    self._save_artifact(artifact)
                    report["accepted"] += 1
                    report["artifacts"].append(asdict(artifact))
            if report["errors"]:
                error_message = f"{len(report['errors'])} artifact download(s) failed"
                if end < len(candidates):
                    # Both immutable Raw and jsDelivr routes were attempted. Keep
                    # the evidence but advance so one bad file cannot starve the
                    # remainder of a large repository forever.
                    report["status"] = "continuing"
                    self._save_cursor(
                        repo, branch, completed_revision, error_message,
                        pending_revision=revision, position=end,
                    )
                else:
                    report["status"] = "partial"
                    self._save_cursor(repo, branch, revision, error_message)
            elif end < len(candidates):
                report["status"] = "continuing"
                self._save_cursor(
                    repo, branch, completed_revision,
                    pending_revision=revision, position=end,
                )
            else:
                report["status"] = "success"
                self._save_cursor(repo, branch, revision)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            report["errors"].append({"scope": scope, "error": message})
            # Preserve the last fully processed revision. The attempted revision
            # remains in the report, while the cursor guarantees a later retry.
            completed, pending, position = self._cursor_state(repo, branch)
            self._save_cursor(
                repo, branch, completed, message,
                pending_revision=pending, position=position,
            )
        return report


def load_watched_github_repos(path: str | Path) -> list[tuple[str, str]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    repos: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in data:
        if not isinstance(item, dict) or item.get("enabled", True) is False:
            continue
        repo = str(item.get("repo", "")).strip().strip("/")
        branch = str(item.get("branch", "main")).strip()
        key = (repo, branch)
        if len(repo.split("/")) == 2 and branch and key not in seen:
            seen.add(key)
            repos.append(key)
    return repos


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DATA_DIR / "sources.db"))
    parser.add_argument("--watch", default=str(CONFIG_DIR / "watch-repos.json"))
    parser.add_argument("--report", default=str(REPORT_DIR / "github-discovery-report.json"))
    args = parser.parse_args()
    collector = GitHubCollector(args.db)
    results = [collector.collect_repo(repo, branch) for repo, branch in load_watched_github_repos(args.watch)]
    report = {"generated_at": _now(), "connector": "github", "results": results}
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
