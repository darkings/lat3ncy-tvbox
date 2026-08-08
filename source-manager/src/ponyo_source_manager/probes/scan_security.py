#!/usr/bin/env python3
"""静态安全扫描：文本危险规则匹配 + jar md5 完整性校验（纯函数段）。"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sqlite3
import urllib.error
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from ponyo_source_manager.core import net
from ponyo_source_manager.core.common import DATA_DIR, assert_no_proxy, strip_md5

MAX_JAR_BYTES = 32 * 1024 * 1024
MAX_JAR_ENTRIES = 20_000
MAX_JAR_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
JAR_FETCH_TIMEOUT_SECONDS = 60.0

# 已批准并物化的 jar 本地缓存（materialize_approved_assets 输出）,
# 按 content_sha256 命名。命中缓存的 jar 无需重复下载（无代理环境下
# 大量无效 jar 引用的网络超时是 scan_security 每轮 4 小时+ 的根源）。
APPROVED_JAR_DIR = DATA_DIR / "approved-assets" / "jar"

_SECRET_RE = re.compile(
    r"(?i)(token|password|authorization)\s*[=:]\s*(?:basic\s+)?[\"']?([^\s\"'<>]{6,})"
)

_FALLBACK_RULES = [
    {
        "rule_id": "suspect-killProcess",
        "pattern": r"android\.os\.Process\.killProcess",
        "severity": "high",
    },
    {
        "rule_id": "suspect-SystemExit",
        "pattern": r"System\.exit\s*\(",
        "severity": "high",
    },
    {
        "rule_id": "suspect-RuntimeExec",
        "pattern": r"Runtime\.getRuntime\(\)\.exec",
        "severity": "high",
    },
    {
        "rule_id": "suspect-Base64APK",
        "pattern": r"base64.*(?:UEsDBBQ|PK\x03\x04)",
        "severity": "high",
    },
]


def load_rules(path: str) -> list[dict]:
    try:
        rules = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        rules = []
    # Merge fallbacks
    existing_ids = {r["rule_id"] for r in rules}
    for fr in _FALLBACK_RULES:
        if fr["rule_id"] not in existing_ids:
            rules.append(fr)
    return rules


def sanitize_evidence(text: str, start: int, end: int, width: int = 160) -> str:
    lo = max(0, start - width // 4)
    hi = min(len(text), end + width // 2)
    snippet = text[lo:hi].replace("\n", " ").replace("\r", " ")
    snippet = _SECRET_RE.sub(lambda m: f"{m.group(1)}={'*' * 4}", snippet)
    return snippet[:width]


def match_text_rules(text: str, rules: list[dict]) -> list[dict]:
    out = []
    for rule in rules:
        m = re.search(rule["pattern"], text)
        if m:
            out.append(
                {
                    "rule_id": rule["rule_id"],
                    "severity": rule["severity"],
                    "evidence": sanitize_evidence(text, m.start(), m.end()),
                }
            )
    return out


def check_jar_md5(declared_md5, jar_bytes, host, allow_hosts) -> dict | None:
    declared = (declared_md5 or "").strip().lower()
    if declared:
        actual = hashlib.md5(jar_bytes).hexdigest()
        if actual != declared:
            return {
                "rule_id": "jar-md5-mismatch",
                "severity": "high",
                "evidence": f"declared={declared[:12]}.. actual={actual[:12]}..",
            }
        return None
    if host in allow_hosts:
        return {
            "rule_id": "jar-unpinned",
            "severity": "low",
            "evidence": f"no md5 declared, host allowlisted: {host}",
        }
    return {
        "rule_id": "jar-unverified",
        "severity": "medium",
        "evidence": f"no md5 declared, host not allowlisted: {host}",
    }


def inspect_jar_bytes(
    declared_md5: str,
    jar_bytes: bytes,
    host: str,
    allow_hosts: set[str],
) -> dict:
    """Validate JAR structure and hashes without loading or decompiling code."""
    actual_md5 = hashlib.md5(jar_bytes).hexdigest()
    sha256 = hashlib.sha256(jar_bytes).hexdigest()
    findings: list[dict] = []
    md5_finding = check_jar_md5(declared_md5, jar_bytes, host, allow_hosts)
    if md5_finding:
        findings.append(md5_finding)
    metadata = {
        "actual_md5": actual_md5,
        "content_sha256": sha256,
        "size_bytes": len(jar_bytes),
        "archive_entry_count": 0,
    }
    if not jar_bytes.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        findings.append(
            {
                "rule_id": "jar-invalid-format",
                "severity": "high",
                "evidence": "downloaded file is not a ZIP/JAR archive",
            }
        )
        return {"validation_status": "invalid", "findings": findings, **metadata}
    try:
        with zipfile.ZipFile(io.BytesIO(jar_bytes)) as archive:
            entries = archive.infolist()
    except (zipfile.BadZipFile, OSError) as exc:
        findings.append(
            {
                "rule_id": "jar-invalid-archive",
                "severity": "high",
                "evidence": f"ZIP directory cannot be parsed: {type(exc).__name__}",
            }
        )
        return {"validation_status": "invalid", "findings": findings, **metadata}

    metadata["archive_entry_count"] = len(entries)
    uncompressed = sum(max(0, int(item.file_size)) for item in entries)
    compressed = sum(max(0, int(item.compress_size)) for item in entries)
    if len(entries) > MAX_JAR_ENTRIES or uncompressed > MAX_JAR_UNCOMPRESSED_BYTES:
        findings.append(
            {
                "rule_id": "jar-archive-bomb",
                "severity": "high",
                "evidence": f"entries={len(entries)} uncompressed={uncompressed}",
            }
        )
    elif compressed and uncompressed / compressed > 1_000:
        findings.append(
            {
                "rule_id": "jar-suspicious-compression",
                "severity": "high",
                "evidence": f"compression_ratio={uncompressed / compressed:.1f}",
            }
        )
    if any(item.flag_bits & 0x1 for item in entries):
        findings.append(
            {
                "rule_id": "jar-encrypted-entry",
                "severity": "high",
                "evidence": "archive contains encrypted entries",
            }
        )
    suspicious = sorted(
        {
            item.filename
            for item in entries
            if item.filename.lower().endswith((".apk", ".dex", ".so", ".exe", ".dll"))
        }
    )
    if suspicious:
        findings.append(
            {
                "rule_id": "jar-embedded-binary",
                "severity": "medium",
                "evidence": "embedded binary entries: " + ", ".join(suspicious[:5]),
            }
        )
    has_java_content = any(
        item.filename.upper() == "META-INF/MANIFEST.MF"
        or item.filename.lower().endswith(".class")
        for item in entries
    )
    if not has_java_content:
        findings.append(
            {
                "rule_id": "jar-missing-java-content",
                "severity": "high",
                "evidence": "archive has neither Java classes nor a JAR manifest",
            }
        )

    severities = {finding["severity"] for finding in findings}
    non_pin_severities = {
        finding["severity"]
        for finding in findings
        if finding["rule_id"] not in {"jar-unpinned", "jar-unverified"}
    }
    if "high" in severities:
        status = "invalid"
    elif "medium" in non_pin_severities:
        status = "review_required"
    elif not declared_md5:
        status = "unpinned"
    elif "medium" in severities:
        status = "review_required"
    else:
        status = "verified"
    return {"validation_status": status, "findings": findings, **metadata}


_GH_PROXY_PREFIX = "https://gh-proxy.com/"
# raw.liucn.cc/box/* is occasionally slow to serve jars; the same bytes are
# published to liu673cn/box@main (blob sha256 verified at approval time).
_LIUCN_GH_MIRROR = ("https://raw.liucn.cc/box/(.+)", "liu673cn/box", "main")


def _jar_fetch_candidates(url: str) -> list[str]:
    """Return equivalent GitHub CDN/raw URLs, verified accelerator first.

    jsDelivr returns HTTP 403 for every .jar under gaotianliuyun/gao, and
    direct raw.githubusercontent.com reads are too slow for the 60s fetch
    window from the no-proxy host. gh-proxy.com is the only CDN verified to
    serve the full jar within seconds on jie; it stays first, the raw URL
    preserves provenance, and the original URL remains as a last fallback.
    """
    liucn = re.match(_LIUCN_GH_MIRROR[0], url)
    if liucn:
        gh_raw = (
            f"https://raw.githubusercontent.com/{_LIUCN_GH_MIRROR[1]}/"
            f"{_LIUCN_GH_MIRROR[2]}/{liucn.group(1)}"
        )
        return [url, _GH_PROXY_PREFIX + gh_raw, gh_raw]
    jsdelivr = re.match(
        r"^https://cdn\.jsdelivr\.net/gh/([^/]+/[^/@]+)@([^/]+)/(.+)$", url
    )
    raw = re.match(
        r"^https://raw\.githubusercontent\.com/([^/]+/[^/]+)/([^/]+)/(.+)$", url
    )
    if jsdelivr:
        repo, branch, path = jsdelivr.groups()
        raw_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
    elif raw:
        raw_url = url
    else:
        return [url]
    candidates = [_GH_PROXY_PREFIX + raw_url, raw_url]
    if jsdelivr:
        candidates.append(url)
    return list(dict.fromkeys(candidates))


def _fetch_jar(fetch_bytes, url: str) -> tuple[bytes, str]:
    failures = []
    for candidate in _jar_fetch_candidates(url):
        try:
            try:
                payload = fetch_bytes(
                    candidate,
                    timeout=JAR_FETCH_TIMEOUT_SECONDS,
                    max_bytes=MAX_JAR_BYTES,
                )
            except TypeError:
                payload = fetch_bytes(candidate)
            return payload, candidate
        except Exception as exc:
            # HTTP 404 是确定性结果（jar 在源上不存在），继续试 raw 只会
            # 多等 60s 超时；直接放弃后续候选。
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 404:
                raise RuntimeError(
                    f"{candidate}: HTTP 404 (jar does not exist); "
                    + "; ".join(failures)
                )
            failures.append(f"{candidate}: {type(exc).__name__}: {str(exc)[:120]}")
    raise RuntimeError("; ".join(failures))


_TEXT_EXT = (".js", ".py", ".txt", ".json")


def _asset_type(url: str) -> str:
    path = urlsplit(strip_md5(url)).path.lower()
    for ext in (".js", ".py", ".txt", ".json", ".jar"):
        if path.endswith(ext):
            return ext[1:]
    return "txt"


def _is_dynamic_local_api(url: str) -> bool:
    """Dynamic DRPY search endpoints are connectivity evidence, not code assets."""
    try:
        parts = urlsplit(strip_md5(url))
        return (
            parts.scheme == "http"
            and parts.hostname in {"127.0.0.1", "::1"}
            and parts.port == 5757
            and parts.path.startswith("/api/")
            and not parts.username
            and not parts.password
        )
    except ValueError:
        return False


def run_scan(
    db_path,
    rules_path,
    allowlist_path,
    report_path,
    *,
    fetch_text=net.fetch_text,
    fetch_bytes=net.fetch_bytes,
    now=None,
    jar_only: bool = False,
) -> dict:
    if assert_no_proxy():
        raise SystemExit("代理环境变量非空，安全扫描中止（需无代理）。")
    now = now or datetime.now(timezone.utc).isoformat()
    rules = load_rules(rules_path)
    try:
        allow_hosts = set(json.loads(Path(allowlist_path).read_text(encoding="utf-8")))
    except Exception:
        allow_hosts = set()
    # timeout 是 sqlite busy timeout：其他阶段进程写入时可等待，避免直接崩溃。
    con = sqlite3.connect(db_path, timeout=60)
    rows = con.execute("""
        SELECT n.fingerprint, n.required_urls, n.jar_md5, r.raw_json
        FROM norm_source n
        JOIN raw_source r ON n.raw_id = r.id
    """).fetchall()
    fps = {}
    for fp, req, jar_md5, raw_json in rows:
        fps.setdefault(
            fp,
            {
                "urls": set(),
                "jar_md5": jar_md5 or "",
                "jar_md5_by_url": {},
                "raw_json": raw_json or "",
            },
        )
        fps[fp]["urls"].update(json.loads(req or "[]"))
    has_dependency_table = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='dependency_asset_evidence'"
    ).fetchone()
    dependency_rows = []
    jar_local_sha: dict[tuple[str, str], str] = {}
    if has_dependency_table:
        # content_sha256 列在部分测试 fixture/旧库中不存在，需先探测列
        has_sha_col = con.execute(
            "SELECT COUNT(*) FROM pragma_table_info('dependency_asset_evidence') "
            "WHERE name='content_sha256'"
        ).fetchone()[0]
        sha_select = ",content_sha256" if has_sha_col else ",NULL"
        dependency_rows = con.execute(
            "SELECT id,fingerprint,effective_url,asset_type,declared_md5,"
            f"resolution_status{sha_select} FROM dependency_asset_evidence"
        ).fetchall()
        for (
            _asset_id,
            fp,
            effective_url,
            asset_type,
            declared_md5,
            _status,
            content_sha256,
        ) in dependency_rows:
            if fp not in fps:
                continue
            if effective_url:
                fps[fp]["urls"].add(effective_url)
                if asset_type == "jar":
                    fps[fp]["jar_md5_by_url"][effective_url] = declared_md5 or ""
                    if content_sha256:
                        jar_local_sha[(fp, effective_url)] = str(content_sha256).lower()
    findings = []  # (fp, url, asset_type, rule_id, severity, evidence)
    text_cache: dict[str, str] = {}
    binary_cache: dict[str, tuple[bytes, str] | Exception] = {}
    summary = {
        "scanned_urls": 0,
        "fetch_errors": 0,
        "jar_assets": sum(1 for row in dependency_rows if row[3] == "jar"),
        "jar_verified": 0,
        "jar_unpinned": 0,
        "jar_review_required": 0,
        "jar_invalid": 0,
        "jar_unresolved": 0,
        "jar_fetch_errors": 0,
        "skipped_recent_failed_jar": 0,
        "skipped_recent_fetched_jar": 0,
        "skipped_recent_text": 0,
        "skipped_dynamic_urls": 0,
        "retained_prior_jar_results": 0,
    }
    seen_issues = set()
    # 每处理一批 jar 就 commit：长事务会持写锁 90+ 分钟，阻塞同库的其他阶段
    # （probe_conn/maccms_collector 写入直接 database is locked 崩溃）。
    jar_updates = 0
    text_updates = 0
    for (
        asset_id,
        fp,
        effective_url,
        asset_type,
        _declared_md5,
        resolution_status,
        _content_sha256,
    ) in dependency_rows:
        if jar_only and asset_type != "jar":
            continue
        if effective_url and resolution_status in {
            "absolute",
            "resolved",
            "not_relative",
        }:
            continue
        summary["jar_unresolved"] += int(asset_type == "jar")
        issue_key = (
            fp,
            effective_url or f"dependency:{asset_id}",
            "dependency-unresolved",
        )
        if issue_key not in seen_issues:
            findings.append(
                (
                    fp,
                    effective_url or f"dependency:{asset_id}",
                    asset_type,
                    "dependency-unresolved",
                    "medium",
                    f"source dependency resolution status: {resolution_status}",
                )
            )
            seen_issues.add(issue_key)
        con.execute(
            "UPDATE dependency_asset_evidence SET fetch_status='not_fetchable',"
            "validation_status='unresolved',last_error=?,scanned_at=? WHERE id=?",
            (f"resolution_status={resolution_status}", now, asset_id),
        )
    con.commit()  # 立即释放写锁，后续网络抓取期间不阻塞同库其他阶段
    for fp, info in fps.items():
        # Scan raw_json itself
        if info["raw_json"] and not jar_only:
            for h in match_text_rules(info["raw_json"], rules):
                issue_key = (fp, "inline:raw_json", h["rule_id"])
                if issue_key not in seen_issues:
                    findings.append(
                        (
                            fp,
                            "inline:raw_json",
                            "json",
                            h["rule_id"],
                            h["severity"],
                            h["evidence"],
                        )
                    )
                    seen_issues.add(issue_key)
        # Scan required urls
        for url in sorted(info["urls"]):
            if net.classify_url(url) == "template":
                continue
            if _is_dynamic_local_api(url):
                summary["skipped_dynamic_urls"] += 1
                continue
            atype = _asset_type(url)
            if jar_only and atype != "jar":
                continue
            try:
                if atype == "jar":
                    host = urlsplit(strip_md5(url)).hostname or ""
                    declared_md5 = info["jar_md5_by_url"].get(url, info["jar_md5"])
                    # 已批准 jar 优先读本地物化缓存，避免每轮重复下载超时
                    cached_jar = None
                    local_sha = jar_local_sha.get((fp, url))
                    if local_sha:
                        cached_path = APPROVED_JAR_DIR / f"{local_sha}.jar"
                        if cached_path.is_file():
                            cached_jar = cached_path.read_bytes()
                    if url not in binary_cache and cached_jar is not None:
                        binary_cache[url] = (cached_jar, "local:approved-assets")
                    if url not in binary_cache:
                        # 冷却窗口：24h 内失败的 jar 不重复尝试（无效引用每轮拖 60s+ 超时）；
                        # 24h 内已成功抓取过的 jar 同样跳过（jar 内容不可变，哈希已入 evidence）
                        prior = con.execute(
                            "SELECT fetch_status FROM dependency_asset_evidence "
                            "WHERE fingerprint=? AND effective_url=? AND asset_type='jar' "
                            "AND scanned_at >= datetime('now','-24 hours')",
                            (fp, url),
                        ).fetchone()
                        if prior and prior[0] == "failed":
                            summary["skipped_recent_failed_jar"] += 1
                            continue
                        if prior and prior[0] == "fetched":
                            summary["skipped_recent_fetched_jar"] += 1
                            continue
                        try:
                            con.commit()  # 网络抓取前释放写锁
                            binary_cache[url] = _fetch_jar(fetch_bytes, url)
                        except Exception as fetch_exc:
                            binary_cache[url] = fetch_exc
                    cached = binary_cache[url]
                    if isinstance(cached, Exception):
                        raise cached
                    jar_bytes, fetched_url = cached
                    inspection = inspect_jar_bytes(
                        declared_md5, jar_bytes, host, allow_hosts
                    )
                    status = inspection["validation_status"]
                    summary[f"jar_{status}"] += 1
                    for finding in inspection["findings"]:
                        issue_key = (fp, url, finding["rule_id"])
                        if issue_key not in seen_issues:
                            findings.append(
                                (
                                    fp,
                                    url,
                                    atype,
                                    finding["rule_id"],
                                    finding["severity"],
                                    finding["evidence"],
                                )
                            )
                            seen_issues.add(issue_key)
                    if has_dependency_table:
                        con.execute(
                            "UPDATE dependency_asset_evidence SET fetch_status='fetched',"
                            "fetched_url=?,actual_md5=?,content_sha256=?,size_bytes=?,"
                            "archive_entry_count=?,validation_status=?,last_error=NULL,"
                            "scanned_at=? WHERE fingerprint=? AND effective_url=? "
                            "AND asset_type='jar'",
                            (
                                fetched_url,
                                inspection["actual_md5"],
                                inspection["content_sha256"],
                                inspection["size_bytes"],
                                inspection["archive_entry_count"],
                                status,
                                now,
                                fp,
                                url,
                            ),
                        )
                    jar_updates += 1
                    if jar_updates % 25 == 0:
                        con.commit()
                else:
                    if url not in text_cache:
                        # 文本 URL 冷却：24h 内抓取过（成功/失败）的跳过，
                        # 避免 drpy 规则等静态文本每轮重复 fetch_text（12s 超时）
                        prior_text = con.execute(
                            "SELECT fetch_status FROM dependency_asset_evidence "
                            "WHERE fingerprint=? AND effective_url=? "
                            "AND asset_type=? "
                            "AND scanned_at >= datetime('now','-24 hours')",
                            (fp, url, atype),
                        ).fetchone()
                        if prior_text and prior_text[0] in ("fetched", "failed"):
                            summary["skipped_recent_text"] += 1
                            continue
                        con.commit()  # 网络抓取前释放写锁
                        text_cache[url] = fetch_text(url)
                        if has_dependency_table:
                            existing = con.execute(
                                "SELECT id FROM dependency_asset_evidence "
                                "WHERE fingerprint=? AND effective_url=? "
                                "AND asset_type=?",
                                (fp, url, atype),
                            ).fetchone()
                            if existing:
                                con.execute(
                                    "UPDATE dependency_asset_evidence "
                                    "SET fetch_status='fetched',"
                                    "validation_status='scanned',last_error=NULL,"
                                    "scanned_at=?,last_seen_at=? WHERE id=?",
                                    (now, now, existing[0]),
                                )
                            else:
                                con.execute(
                                    "INSERT INTO dependency_asset_evidence"
                                    "(fingerprint,config_origin,source_field,"
                                    "effective_url,asset_type,resolution_status,"
                                    "fetch_status,validation_status,scanned_at,"
                                    "first_seen_at,last_seen_at) "
                                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                                    (
                                        fp,
                                        "scan_security",
                                        "required_urls",
                                        url,
                                        atype,
                                        "resolved",
                                        "fetched",
                                        "scanned",
                                        now,
                                        now,
                                        now,
                                    ),
                                )
                            text_updates += 1
                            if text_updates % 25 == 0:
                                con.commit()
                    for h in match_text_rules(text_cache[url], rules):
                        issue_key = (fp, url, h["rule_id"])
                        if issue_key not in seen_issues:
                            findings.append(
                                (
                                    fp,
                                    url,
                                    atype,
                                    h["rule_id"],
                                    h["severity"],
                                    h["evidence"],
                                )
                            )
                            seen_issues.add(issue_key)
                summary["scanned_urls"] += 1
            except Exception as scan_exc:
                error_short = f"{type(scan_exc).__name__}: {str(scan_exc)[:120]}"
                error_long = f"{type(scan_exc).__name__}: {str(scan_exc)[:300]}"
                summary["fetch_errors"] += 1
                issue_key = (fp, url, "dependency-fetch-failed")
                if issue_key not in seen_issues:
                    findings.append(
                        (
                            fp,
                            url,
                            atype,
                            "dependency-fetch-failed",
                            "medium",
                            error_short,
                        )
                    )
                    seen_issues.add(issue_key)
                if atype == "jar" and has_dependency_table:
                    summary["jar_fetch_errors"] += 1
                    prior = con.execute(
                        "SELECT validation_status FROM dependency_asset_evidence "
                        "WHERE fingerprint=? AND effective_url=? AND asset_type='jar'",
                        (fp, url),
                    ).fetchone()
                    if prior and prior[0] in {
                        "invalid",
                        "verified",
                        "review_required",
                        "unpinned",
                    }:
                        summary["retained_prior_jar_results"] += 1
                    con.execute(
                        "UPDATE dependency_asset_evidence SET fetch_status='failed',"
                        "validation_status=CASE "
                        "WHEN validation_status IN "
                        "('invalid','verified','review_required','unpinned') "
                        "THEN validation_status ELSE 'fetch_error' END,"
                        "last_error=?,scanned_at=? "
                        "WHERE fingerprint=? AND effective_url=? AND asset_type='jar'",
                        (error_long, now, fp, url),
                    )
                elif atype != "jar" and has_dependency_table:
                    # 文本抓取失败也记录冷却，避免每轮重复 12s 超时
                    existing_text = con.execute(
                        "SELECT id FROM dependency_asset_evidence "
                        "WHERE fingerprint=? AND effective_url=? AND asset_type=?",
                        (fp, url, atype),
                    ).fetchone()
                    if existing_text:
                        con.execute(
                            "UPDATE dependency_asset_evidence "
                            "SET fetch_status='failed',last_error=?,"
                            "scanned_at=?,last_seen_at=? WHERE id=?",
                            (error_long, now, now, existing_text[0]),
                        )
                    else:
                        con.execute(
                            "INSERT INTO dependency_asset_evidence"
                            "(fingerprint,config_origin,source_field,"
                            "effective_url,asset_type,resolution_status,"
                            "fetch_status,validation_status,last_error,scanned_at,"
                            "first_seen_at,last_seen_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                fp,
                                "scan_security",
                                "required_urls",
                                url,
                                atype,
                                "resolved",
                                "failed",
                                "fetch_error",
                                error_long,
                                now,
                                now,
                                now,
                            ),
                        )
                        text_updates += 1
                        if text_updates % 25 == 0:
                            con.commit()
    scanned_fps = list(fps.keys())
    if scanned_fps:
        placeholders = ",".join("?" * len(scanned_fps))
        if jar_only:
            con.execute(
                "DELETE FROM security_finding WHERE asset_type='jar' "
                f"AND fingerprint IN ({placeholders})",
                scanned_fps,
            )
        else:
            con.execute(
                f"DELETE FROM security_finding WHERE fingerprint IN ({placeholders})",
                scanned_fps,
            )
    con.executemany(
        "INSERT INTO security_finding(fingerprint,target_url,asset_type,"
        "rule_id,severity,evidence,scanned_at) VALUES(?,?,?,?,?,?,?)",
        [(f[0], f[1], f[2], f[3], f[4], f[5], now) for f in findings],
    )
    deny_fps = sorted({f[0] for f in findings if f[4] == "high"})
    for fp in deny_fps:
        con.execute(
            "INSERT OR REPLACE INTO list_state(fingerprint,state,reason,updated_at)"
            " VALUES(?,?,?,?)",
            (fp, "deny", "security:high", now),
        )
    con.commit()
    con.close()
    for sev in ("high", "medium", "low"):
        summary[sev] = sum(1 for f in findings if f[4] == sev)
    summary["deny_fps"] = deny_fps
    report = {
        "summary": summary,
        "generated_at": now,
        "findings": [
            {
                "fingerprint": f[0],
                "target_url": f[1],
                "asset_type": f[2],
                "rule_id": f[3],
                "severity": f[4],
                "evidence": f[5],
            }
            for f in sorted(
                findings, key=lambda x: {"high": 0, "medium": 1, "low": 2}[x[4]]
            )
        ],
    }
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return dict(summary)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--rules", default="config/security_rules.json")
    p.add_argument("--allowlist", default="config/allowlist.json")
    p.add_argument("--report", default="reports/security-report.json")
    p.add_argument(
        "--jar-only",
        action="store_true",
        help="只抓取并静态验证 JAR 依赖；不执行或反编译 JAR",
    )
    a = p.parse_args()
    print(
        json.dumps(
            run_scan(a.db, a.rules, a.allowlist, a.report, jar_only=a.jar_only),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
