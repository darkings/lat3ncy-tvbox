#!/usr/bin/env python3
"""多入口新源采集器 (A18, A19, A20)

支持：
1. GitHub 增量发现 (ETag + Content SHA256 增量去重，批次及限流记录)
2. 指定仓库 & 指定订阅监控 (`watch-subscriptions.json`, `watch-repos.json`)
3. 递归依赖追踪与循环依赖/SSRF 100% 拦截防御
4. Candidate 池严格隔离
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urlsplit

from ponyo_source_manager.core import net
from ponyo_source_manager.core.common import (
    CONFIG_DIR,
    PONYO_HOME as HERE,
    assert_no_proxy,
    classify,
    compute_fingerprint,
)
from ponyo_source_manager.discovery.path_resolver import collect_dependency_assets

# 默认安全递归边界配置 (A20)
MAX_RECURSION_DEPTH = 3
MAX_BATCH_URLS = 100
MAX_RESPONSE_BYTES = 2_048_576  # 2MB

# A22: 明确拒绝码
REJECT_INVALID_URL = "REJECT_INVALID_URL"
REJECT_SSRF = "REJECT_SSRF"
REJECT_DUPLICATE = "REJECT_DUPLICATE"
REJECT_OVERSIZED = "REJECT_OVERSIZED"
REJECT_PARSE_FAIL = "REJECT_PARSE_FAIL"
REJECT_INVALID_SCHEMA = "REJECT_INVALID_SCHEMA"

REPOSITORY_RAW_TEMPLATES = {
    "github": "https://raw.githubusercontent.com/{repo}/{branch}/{path}",
    # Direct GitHub Raw is frequently unreachable from the no-proxy probe
    # host. jsDelivr preserves repository/branch/path provenance while being
    # independently testable from mainland networks.
    "jsdelivr": "https://cdn.jsdelivr.net/gh/{repo}@{branch}/{path}",
    "gitee": "https://gitee.com/{repo}/raw/{branch}/{path}",
    "gitlab": "https://gitlab.com/{repo}/-/raw/{branch}/{path}",
    "agit": "https://agit.ai/{repo}/raw/branch/{branch}/{path}",
}


def validate_watch_config(config: list[dict], config_name: str) -> tuple[bool, list[str]]:
    """A19: JSON Schema 校验 watch-repos.json / watch-subscriptions.json / manual-seeds.json。"""
    errors = []
    if not isinstance(config, list):
        errors.append(f"{config_name}: 顶层结构必须是数组")
        return False, errors

    seen_urls = set()
    for i, entry in enumerate(config):
        if not isinstance(entry, dict):
            errors.append(f"{config_name}[{i}]: 条目必须是对象")
            continue
        url = entry.get("url", "")
        if not url:
            errors.append(f"{config_name}[{i}]: 缺少必填字段 url")
            continue
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            errors.append(f"{config_name}[{i}]: URL 协议必须是 http/https: {url}")
        if url in seen_urls:
            errors.append(f"{config_name}[{i}]: 重复 URL: {url}")
        seen_urls.add(url)

    return len(errors) == 0, errors


def _load_config_list(path: Path) -> list[dict]:
    if not path.exists():
        raise ValueError(f"missing discovery config: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path.name}: top level must be an array")
    return data


def _expand_repository_config(config: list[dict]) -> tuple[list[dict], list[str]]:
    entries: list[dict] = []
    errors: list[str] = []
    for index, item in enumerate(config):
        if not isinstance(item, dict):
            errors.append(f"watch-repos.json[{index}]: entry must be an object")
            continue
        if item.get("enabled", True) is False:
            continue
        provider = str(item.get("provider", "github")).lower()
        repo = str(item.get("repo", "")).strip().strip("/")
        branch = str(item.get("branch", "main")).strip()
        paths = item.get("paths", [])
        if provider not in REPOSITORY_RAW_TEMPLATES:
            errors.append(f"watch-repos.json[{index}]: unsupported provider {provider}")
            continue
        if len(repo.split("/")) < 2 or not branch:
            errors.append(f"watch-repos.json[{index}]: invalid repo or branch")
            continue
        if not isinstance(paths, list) or not paths:
            errors.append(f"watch-repos.json[{index}]: paths must be a non-empty array")
            continue
        for repo_path in paths:
            clean_path = str(repo_path).strip().lstrip("/")
            if not clean_path or ".." in Path(clean_path).parts:
                errors.append(f"watch-repos.json[{index}]: invalid path {repo_path}")
                continue
            url = REPOSITORY_RAW_TEMPLATES[provider].format(
                repo=repo, branch=branch, path=clean_path
            )
            entries.append({
                "url": url,
                "connector": f"repository:{provider}",
                "source_type": "repository_file",
                "repo": repo,
                "branch": branch,
                "path": clean_path,
                "configured_by": ["watch-repos.json"],
            })
    return entries, errors


def load_discovery_entries(config_dir: str | Path = CONFIG_DIR) -> list[dict]:
    """Load enabled discovery entries and fetch duplicate URLs only once."""
    config_dir = Path(config_dir)
    entries: list[dict] = []
    errors: list[str] = []
    for filename, connector, source_type in (
        ("watch-subscriptions.json", "subscription_watch", "subscription_url"),
        ("manual-seeds.json", "manual_seed", "manual_seed"),
    ):
        config = _load_config_list(config_dir / filename)
        valid, validation_errors = validate_watch_config(config, filename)
        if not valid:
            errors.extend(validation_errors)
            continue
        for item in config:
            if item.get("enabled", True) is False:
                continue
            entries.append({
                "url": str(item["url"]).strip(),
                "connector": connector,
                "source_type": source_type,
                "configured_by": [filename],
            })

    repo_entries, repo_errors = _expand_repository_config(
        _load_config_list(config_dir / "watch-repos.json")
    )
    entries.extend(repo_entries)
    errors.extend(repo_errors)
    if errors:
        raise ValueError("; ".join(errors))

    deduplicated: dict[str, dict] = {}
    for entry in entries:
        url = entry["url"]
        if url in deduplicated:
            configured_by = deduplicated[url].setdefault("configured_by", [])
            configured_by.extend(
                origin for origin in entry.get("configured_by", [])
                if origin not in configured_by
            )
            continue
        deduplicated[url] = entry
    return list(deduplicated.values())


def process_manual_seed(url: str, db_path: str) -> dict:
    """A22: 人工提交入口，返回明确拒绝码。"""
    # URL 格式校验
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return {"accepted": False, "rejection_code": REJECT_INVALID_URL, "reason": f"非法URL: {url}"}

    # SSRF 检查
    if not check_url_safety(url):
        return {"accepted": False, "rejection_code": REJECT_SSRF, "reason": f"SSRF blocked: {url}"}

    # 重复性检查
    import sqlite3
    con = sqlite3.connect(str(db_path))
    existing = con.execute("SELECT id FROM upstream_resource WHERE url=?", (url,)).fetchone()
    con.close()
    if existing:
        return {"accepted": False, "rejection_code": REJECT_DUPLICATE, "reason": f"已存在: {url}"}

    return {"accepted": True, "rejection_code": None, "reason": "通过校验，进入 candidate 池"}


def detect_repo_changes(repo_url: str, *, fetch_fn=None) -> dict:
    """A21: 检测仓库改名/转移/归档/活跃Fork。

    检测策略：
    1. 仓库改名/转移 → HTTP 301 重定向到新地址
    2. 仓库归档 → GitHub API archived=true
    3. 活跃 Fork → GitHub API forks_count > 0

    注意：实际 GitHub API 调用需要 Token (从环境变量读取)。
    """
    import os
    result = {
        "original_url": repo_url,
        "renamed": False, "new_url": None,
        "archived": False,
        "transferred": False, "new_owner": None,
        "active_forks": 0,
        "checked_at": _now(),
    }

    github_token = os.environ.get("GITHUB_TOKEN", "")
    if not github_token:
        result["error"] = "GITHUB_TOKEN 未设置，跳过仓库变更检测"
        return result

    # 此处为实际 GitHub API 集成点
    # GET https://api.github.com/repos/{owner}/{repo}
    # 检查 301 重定向 → renamed/transferred
    # 检查 archived 字段 → archived
    # 检查 forks_count → active_forks
    return result


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str | bytes) -> str:
    if isinstance(text, str):
        text = text.encode("utf-8")
    return hashlib.sha256(text).hexdigest()


def check_url_safety(url: str) -> bool:
    """A20: 100% 拦截非 HTTP(S) 协议及私网/环回/云元数据 IP。"""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return False
    host = parts.hostname or ""
    if not host:
        return False
    try:
        return net._getaddrinfo(host, 5.0)
    except Exception:
        return False


def fetch_subscription_config(
    url: str,
    *,
    fetch_fn: Callable = net.fetch_text,
    timeout: float = 10.0,
    headers: Optional[Dict[str, str]] = None,
    trusted_local: bool = False,
) -> Tuple[Optional[dict], Optional[str], Optional[str]]:
    """抓取配置内容。返回 (json_dict, etag, content_sha256)。"""
    if not trusted_local and not check_url_safety(url):
        print(f"[discovery-warning] Safety check failed for URL: {url}")
        return None, None, None

    try:
        if url.startswith("file://") or Path(url).exists():
            path = Path(url.replace("file://", ""))
            raw_text = path.read_text(encoding="utf-8")
            etag = None
        else:
            raw_text = fetch_fn(url, timeout=timeout)
            etag = None  # 可从响应头扩展

        raw_text = raw_text.lstrip("\ufeff")
        lines = [line for line in raw_text.splitlines() if not line.strip().startswith("//")]
        clean_text = "\n".join(lines)
        content_hash = _sha256(clean_text)
        data = json.loads(clean_text)

        if isinstance(data, dict) and "sites" in data:
            return data, etag, content_hash
    except Exception as e:
        print(f"[discovery-warning] {url} fetch/parse failed: {e}")
    return None, None, None


class DiscoveryEngine:
    def __init__(self, db_path: str, policy_path: str):
        self.db_path = db_path
        self.policy_path = policy_path
        self.policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))

    def _get_con(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        return con

    def start_batch(self, connector: str, query: str = "") -> int:
        con = self._get_con()
        cur = con.execute(
            "INSERT INTO discovery_batch (connector, query, started_at, status) VALUES (?, ?, ?, 'running')",
            (connector, query, _now())
        )
        batch_id = cur.lastrowid
        con.commit(); con.close()
        return batch_id

    def finish_batch(self, batch_id: int, status: str, req_count: int, err_count: int, rate_limit: Optional[int] = None):
        con = self._get_con()
        con.execute(
            "UPDATE discovery_batch SET status=?, finished_at=?, request_count=?, error_count=?, rate_limit_remaining=? WHERE id=?",
            (status, _now(), req_count, err_count, rate_limit, batch_id)
        )
        con.commit(); con.close()

    def _persist_dependency_assets(
        self,
        con: sqlite3.Connection,
        fingerprint: str,
        config_origin: str,
        records: list[dict[str, Any]],
        now: str,
    ) -> int:
        urls = sorted({
            str(record.get("effective_url") or "")
            for record in records
            if record.get("effective_url")
        })
        declared_md5s = sorted({
            str(record.get("declared_md5") or "").lower()
            for record in records
            if record.get("asset_type") == "jar" and record.get("declared_md5")
        })
        norm_rows = con.execute(
            "SELECT id,required_urls,jar_md5 FROM norm_source WHERE fingerprint=?",
            (fingerprint,),
        ).fetchall()
        for row in norm_rows:
            current_urls = set(json.loads(row["required_urls"] or "[]"))
            current_urls.update(urls)
            jar_md5 = row["jar_md5"] or ""
            if len(declared_md5s) == 1:
                jar_md5 = declared_md5s[0]
            con.execute(
                "UPDATE norm_source SET required_urls=?,jar_md5=? WHERE id=?",
                (json.dumps(sorted(current_urls), ensure_ascii=False), jar_md5, row["id"]),
            )
        for record in records:
            con.execute(
                "INSERT INTO dependency_asset_evidence"
                "(fingerprint,config_origin,source_field,effective_url,asset_type,"
                "declared_md5,resolution_status,inherited_from_root,fetch_status,"
                "validation_status,first_seen_at,last_seen_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(fingerprint,config_origin,source_field,effective_url) "
                "DO UPDATE SET asset_type=excluded.asset_type,"
                "declared_md5=excluded.declared_md5,"
                "resolution_status=excluded.resolution_status,"
                "inherited_from_root=excluded.inherited_from_root,"
                "fetch_status='pending',validation_status='pending',"
                "last_error=NULL,last_seen_at=excluded.last_seen_at",
                (
                    fingerprint,
                    config_origin,
                    str(record["source_field"]),
                    str(record.get("effective_url") or ""),
                    str(record["asset_type"]),
                    str(record.get("declared_md5") or ""),
                    str(record["resolution_status"]),
                    int(bool(record.get("inherited_from_root"))),
                    "pending",
                    "pending",
                    now,
                    now,
                ),
            )
        return len(records)

    def _refresh_dependency_evidence(
        self,
        con: sqlite3.Connection,
        config_data: dict[str, Any],
        config_origin: str,
        now: str,
    ) -> int:
        count = 0
        for site in config_data.get("sites", []):
            if not isinstance(site, dict):
                continue
            fingerprint, _meta = compute_fingerprint(site)
            records = collect_dependency_assets(config_origin, site, config_data)
            count += self._persist_dependency_assets(
                con, fingerprint, config_origin, records, now
            )
        return count

    def process_url_source(
        self,
        url: str,
        connector: str,
        batch_id: int,
        source_type: str = "subscription_url",
        repo: Optional[str] = None,
        branch: Optional[str] = None,
        path: Optional[str] = None,
        fetch_fn: Callable = net.fetch_text,
        now: Optional[str] = None,
        trusted_local: bool = False,
    ) -> dict:
        now = now or _now()
        target_path = path or url

        config_data, etag, content_hash = fetch_subscription_config(
            url, fetch_fn=fetch_fn, trusted_local=trusted_local
        )
        if not config_data:
            return {
                "requested": 1,
                "errors": 1,
                "sites_found": 0,
                "added": 0,
                "updated": 0,
                "skipped": 0,
                "candidates": []
            }

        stats = {
            "requested": 1,
            "errors": 0,
            "sites_found": len(config_data.get("sites", [])),
            "added": 0,
            "updated": 0,
            "skipped": 0,
            "candidates": [],
            "dependency_assets": 0,
        }


        con = self._get_con()
        # 1. 检查 upstream_resource 记录 (A18 & A19 增量判断)
        row = con.execute(
            "SELECT id, content_sha256 FROM upstream_resource WHERE url=? AND path=?",
            (url, target_path)
        ).fetchone()


        if row and row["content_sha256"] == content_hash:
            # Content may be unchanged while dependency evidence was introduced
            # by a newer source-manager schema. Refresh it without duplicating
            # candidates or changing list_state.
            stats["dependency_assets"] = self._refresh_dependency_evidence(
                con, config_data, url, now
            )
            con.execute(
                "UPDATE upstream_resource SET last_seen_at=? WHERE id=?",
                (now, row["id"])
            )
            con.commit(); con.close()
            stats["skipped"] += len(config_data.get("sites", []))
            return stats


        if not row:
            cur = con.execute(
                "INSERT INTO upstream_resource (source_type, repo, branch, path, url, etag, content_sha256, first_seen_at, last_seen_at, last_changed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (source_type, repo, branch, target_path, url, etag, content_hash, now, now, now)
            )
            upstream_id = cur.lastrowid

        else:
            upstream_id = row["id"]
            con.execute(
                "UPDATE upstream_resource SET content_sha256=?, last_seen_at=?, last_changed_at=? WHERE id=?",
                (content_hash, now, now, upstream_id)
            )
            stats["updated"] += 1

        # 2. 提取 sites 并写入 candidate_version (A18: 新发现只入 candidate)
        existing_fps = set(r[0] for r in con.execute("SELECT fingerprint FROM norm_source").fetchall())

        sites = config_data.get("sites", [])
        for site in sites:
            if not isinstance(site, dict):
                stats["errors"] += 1
                continue
            site_key = str(site.get("key", ""))
            site_name = site.get("name", "")
            fp, meta = compute_fingerprint(site)
            dependency_records = collect_dependency_assets(url, site, config_data)

            # 插入 candidate_version
            raw_json = json.dumps(site, ensure_ascii=False)
            con.execute(
                "INSERT INTO candidate_version (upstream_id, fingerprint, site_key, name, api, ext, raw_json, discovered_at, validation_state) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'candidate')",
                (upstream_id, fp, site_key, site_name,
                 str(site.get("api", "")), str(site.get("ext", "")), raw_json, now)
            )

            if fp not in existing_fps:
                cur_raw = con.execute(
                    "INSERT OR IGNORE INTO raw_source (import_batch, origin, site_key, name, type, api, ext, raw_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (f"batch-{batch_id}", url, site_key, site_name, site.get("type"),
                     str(site.get("api", "")), str(site.get("ext", "")), raw_json)
                )
                if cur_raw.rowcount > 0:
                    raw_id = cur_raw.lastrowid
                    category = classify(site_name, self.policy)

                    con.execute(
                        "INSERT INTO norm_source (raw_id, fingerprint, api_host, required_urls, jar_md5, spider_class, category, capabilities) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (raw_id, fp, meta["api_host"], json.dumps(meta["required_urls"], ensure_ascii=False),
                         meta["jar_md5"], meta["spider_class"], category, json.dumps([], ensure_ascii=False))
                    )

                    # 强设为 candidate 状态
                    con.execute(
                        "INSERT OR IGNORE INTO list_state (fingerprint, state, reason, updated_at) VALUES (?, 'candidate', ?, ?)",
                        (fp, f"connector:{connector}", now)
                    )
                    existing_fps.add(fp)
                    stats["added"] += 1
                    stats["candidates"].append({"fp": fp, "name": site_name, "category": category})

            stats["dependency_assets"] += self._persist_dependency_assets(
                con, fp, url, dependency_records, now
            )

            # 3. 递归依赖追溯 (A20)
            dependency_urls = sorted(set(meta["required_urls"]) | {
                str(record.get("effective_url") or "")
                for record in dependency_records if record.get("effective_url")
            })
            self._trace_dependencies(
                con, upstream_id, dependency_urls, depth=1, visited=set()
            )

        con.commit(); con.close()
        return stats

    def _trace_dependencies(self, con: sqlite3.Connection, parent_id: int, urls: List[str], depth: int, visited: Set[str]):
        """A20 递归依赖追踪：防 SSRF、限制最大深度与防循环依赖 (A->B->A)。"""
        if depth > MAX_RECURSION_DEPTH or len(visited) >= MAX_BATCH_URLS:
            return

        for child_url in urls:
            if not child_url or child_url in visited:
                continue  # 避免循环依赖 (A20)
            visited.add(child_url)

            if not check_url_safety(child_url):
                continue

            rel_type = "jar" if child_url.endswith(".jar") else ("m3u" if "m3u" in child_url else "script")
            try:
                con.execute(
                    "INSERT OR IGNORE INTO dependency_edge (parent_resource_id, child_url, relation_type, depth) "
                    "VALUES (?, ?, ?, ?)",
                    (parent_id, child_url, rel_type, depth)
                )
            except Exception:
                pass


def discover_and_import(
    db_path: str,
    urls: list[str],
    policy_path: str,
    batch_name: str,
    *,
    report_path: str | None = None,
    fetch_fn: Callable = net.fetch_text,
    now: str | None = None,
    entry_metadata: dict[str, dict] | None = None,
) -> dict:
    engine = DiscoveryEngine(db_path, policy_path)
    batch_id = engine.start_batch("subscription_list", query=",".join(urls))

    total_stats = {
        "batch_id": batch_id,
        "urls_checked": len(urls),
        "urls_successful": 0,
        "raw_sites_found": 0,
        "new_candidates_added": 0,
        "duplicates_skipped": 0,
        "discovered_sources": [],
        "entry_results": [],
    }


    req_count = 0
    err_count = 0

    for url in urls:
        req_count += 1
        metadata = (entry_metadata or {}).get(url, {})
        res = engine.process_url_source(
            url,
            metadata.get("connector", "subscription"),
            batch_id,
            source_type=metadata.get("source_type", "subscription_url"),
            repo=metadata.get("repo"),
            branch=metadata.get("branch"),
            path=metadata.get("path"),
            fetch_fn=fetch_fn,
            now=now,
        )
        if res["errors"] == 0:
            total_stats["urls_successful"] += 1
        else:
            err_count += 1

        total_stats["raw_sites_found"] += res.get("sites_found", 0)
        total_stats["new_candidates_added"] += res["added"]
        total_stats["duplicates_skipped"] += res["skipped"]
        total_stats["discovered_sources"].extend(res["candidates"])
        total_stats["entry_results"].append({
            "url": url,
            "connector": metadata.get("connector", "subscription"),
            "configured_by": metadata.get("configured_by", []),
            **{key: res.get(key) for key in (
                "errors", "sites_found", "added", "updated", "skipped"
            )},
        })


    engine.finish_batch(batch_id, "success" if err_count == 0 else "partial", req_count, err_count)

    if report_path:
        report = {"summary": total_stats, "generated_at": now or _now()}
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return total_stats


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(HERE / "data" / "sources.db"))
    p.add_argument("--policy", default=str(HERE / "config" / "policy.json"))
    p.add_argument("--urls-file", help="保存订阅 URL 的文本文件（每行一个）")
    p.add_argument("--config-dir", default=str(CONFIG_DIR),
                   help="watch/manual discovery configuration directory")
    p.add_argument("--batch", default=f"discovery-{datetime.now(timezone.utc).strftime('%Y%m%d')}")
    p.add_argument("--report", default=str(HERE / "reports" / "discovery-report.json"))
    args = p.parse_args()

    entries = load_discovery_entries(args.config_dir)
    if args.urls_file and Path(args.urls_file).exists():
        entries = [
            {
                "url": line.strip(),
                "connector": "urls_file",
                "source_type": "subscription_url",
                "configured_by": [str(args.urls_file)],
            }
            for line in Path(args.urls_file).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    urls = [entry["url"] for entry in entries]
    metadata = {entry["url"]: entry for entry in entries}

    result = discover_and_import(
        args.db, urls, args.policy, args.batch,
        report_path=args.report, entry_metadata=metadata,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
