#!/usr/bin/env python3
"""静态安全扫描：文本危险规则匹配 + jar md5 完整性校验（纯函数段）。"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
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
# 预留写库/出报告时间，避免跑到 2700s 被 SIGKILL 导致本轮证据全部丢失。
SCAN_FETCH_DEADLINE_SECONDS = 2400.0
# 冷却窗口：同一 URL 任意指纹成功/失败后，其它指纹 24h 内不再打网络。
FETCH_COOLDOWN_HOURS = 24.0

# 方案E：失败 URL 指数退避。
# 原逻辑失败后仅冷却 24h，之后无条件重试。实测失败 URL 理论耗时 11.2h
# （JAR 3 候选 × 8s = 24s/URL），远超 40min 预算，导致 4322 个 URL 被
# skipped_fetch_deadline 跳过。改为按连续失败次数指数退避：
#   第1次 24h / 第2次 48h / 第3次 96h / 第4次 168h(7天) / 第5次+ 336h(14天)
# 死链不再每天消耗预算，预算可分配给真正需要扫描的 URL。
FAIL_BACKOFF_HOURS = (24.0, 48.0, 96.0, 168.0, 336.0)

# 方案E：JAR 抓取超时从 8s 缩短到 5s。
# 实测 gh-proxy.com 正常响应 <2s，8s 对死链是纯浪费。
JAR_FETCH_TIMEOUT_SECONDS = 5.0

# 方案E：连续失败 >= 该次数后，JAR 只试首个候选（gh-proxy），
# 不再回退 raw.githubusercontent.com / 原始 URL，避免 3× 超时。
JAR_SINGLE_CANDIDATE_AFTER_FAILURES = 2

# 方案A：并发预抓取。
# 原实现完全串行抓取，3891 个 URL 在 40min 预算内扫不完
# （skipped_fetch_deadline=1387）。改为按 host 分组并发：
#   - 同 host 串行（防目标限流，RateLimiter 已线程安全）
#   - 跨 host 并发（ThreadPoolExecutor）
# 与 probe_conn 的 16 workers 保持一致。
SCAN_FETCH_WORKERS = 16
# 单批预抓取的 URL 上限，控制内存（并发持有多个 JAR 字节，单个最大 32MB）。
SCAN_PREFETCH_BATCH = 400

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


def _fetch_jar(
    fetch_bytes, url: str, *, single_candidate: bool = False
) -> tuple[bytes, str]:
    """抓取 JAR 字节。

    方案E：``single_candidate=True`` 时只试首个候选（gh-proxy），
    用于连续失败 >= JAR_SINGLE_CANDIDATE_AFTER_FAILURES 的死链，
    避免 3 候选 × 超时 = 3 倍浪费。
    """
    failures = []
    candidates = _jar_fetch_candidates(url)
    if single_candidate:
        candidates = candidates[:1]
    for candidate in candidates:
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


def _cooldown_window_sql() -> str:
    """SQLite datetime() 修饰符，控制跨 fingerprint 的 URL 冷却窗口。"""
    return f"-{FETCH_COOLDOWN_HOURS:g} hours"


def _recent_url_fetch_status(
    con: sqlite3.Connection, url: str, asset_type: str
) -> str | None:
    """查询同一 URL 在冷却窗口内是否已有成功/失败结果。

    只按 effective_url + asset_type 判断，不限定 fingerprint：
    同一 JAR/文本被上百个源引用时，避免对死链重复打网络。
    返回值仅用于决定是否跳过抓取，不改写当前源的安全判定。

    方案E：失败 URL 使用指数退避窗口，而非固定 24h。
    连续失败次数越多，冷却窗口越长（24h -> 48h -> 96h -> 168h -> 336h），
    避免死链每天消耗扫描预算。
    """
    # 成功：固定 24h 冷却
    row = con.execute(
        "SELECT fetch_status FROM dependency_asset_evidence "
        "WHERE effective_url=? AND asset_type=? "
        "AND fetch_status='fetched' "
        "AND scanned_at >= datetime('now', ?) "
        "LIMIT 1",
        (url, asset_type, _cooldown_window_sql()),
    ).fetchone()
    if row is not None:
        return "fetched"

    # 失败：按连续失败次数指数退避
    fail_row = con.execute(
        "SELECT COUNT(*) FROM dependency_asset_evidence "
        "WHERE effective_url=? AND asset_type=? AND fetch_status='failed'",
        (url, asset_type),
    ).fetchone()
    fail_count = int(fail_row[0]) if fail_row else 0
    if fail_count <= 0:
        return None
    backoff_hours = _fail_backoff_hours(fail_count)
    row = con.execute(
        "SELECT fetch_status FROM dependency_asset_evidence "
        "WHERE effective_url=? AND asset_type=? "
        "AND fetch_status='failed' "
        "AND scanned_at >= datetime('now', ?) "
        "LIMIT 1",
        (url, asset_type, f"-{backoff_hours:g} hours"),
    ).fetchone()
    return None if row is None else "failed"


def _fail_backoff_hours(fail_count: int) -> float:
    """按连续失败次数返回退避小时数（方案E）。

    第1次 24h / 第2次 48h / 第3次 96h / 第4次 168h / 第5次+ 336h。
    """
    idx = min(max(fail_count, 1), len(FAIL_BACKOFF_HOURS)) - 1
    return FAIL_BACKOFF_HOURS[idx]


def _url_fail_count(con: sqlite3.Connection, url: str, asset_type: str) -> int:
    """查询某 URL 的历史失败次数，用于决定 JAR 候选数（方案E）。"""
    row = con.execute(
        "SELECT COUNT(*) FROM dependency_asset_evidence "
        "WHERE effective_url=? AND asset_type=? AND fetch_status='failed'",
        (url, asset_type),
    ).fetchone()
    return int(row[0]) if row else 0


def _prefetch_concurrent(
    urls: list[str],
    *,
    con: sqlite3.Connection,
    binary_cache: dict,
    text_cache: dict,
    summary: dict,
    deadline: float,
) -> None:
    """方案A：并发预抓取。

    原实现完全串行抓取，3891 个 URL 在 40min 预算内扫不完。本函数把
    网络抓取提前并发完成并填入缓存，后续串行循环命中缓存后不再打网络，
    业务逻辑（inspect / DB 写入 / 评分）完全不变。

    并发策略：
      * 按 host 分组，同 host 串行 —— 避免触发目标站限流
        （RateLimiter 本身线程安全，但同 host 并发仍会撞 429）
      * 跨 host 并发 —— ThreadPoolExecutor(SCAN_FETCH_WORKERS)
      * 每个 worker 只做网络 IO，不碰 sqlite / findings，避免竞态

    参数：
      urls:          待抓取的 URL 列表（已去重）
      con:           sqlite 连接。仅用于在主线程预读失败次数，
                     不传入 worker（worker 只做网络 IO，不碰 sqlite）。
      binary_cache:  JAR 字节缓存，key=url，value=(bytes, source) 或 Exception
      text_cache:    文本缓存，key=url，value=str
      summary:       统计计数器（仅主线程写，worker 不写）
      deadline:      抓取截止时间（time.monotonic() 基准）
    """
    if not urls:
        return

    # 方案E 修复：在主线程预读每个 JAR URL 的历史失败次数。
    # 原实现只在串行循环里判定 single_candidate，但预抓取先于串行循环执行
    # 并填充 binary_cache，导致串行循环的 `if url not in binary_cache` 直接
    # 跳过，单候选优化永远不生效（jar_single_candidate_fetches 恒为 0）。
    # 这里提前判定，保证并发路径与串行路径语义一致。
    # 注意：sqlite 连接非线程安全，必须在主线程查询，worker 只读该集合。
    single_candidate_urls: set[str] = set()
    for u in urls:
        if _asset_type(u) != "jar":
            continue
        if _url_fail_count(con, u, "jar") >= JAR_SINGLE_CANDIDATE_AFTER_FAILURES:
            single_candidate_urls.add(u)

    # 按 host 分组：同 host 的 URL 放进同一组，组内串行执行
    by_host: dict[str, list[str]] = {}
    for u in urls:
        host = urlsplit(u).hostname or ""
        by_host.setdefault(host, []).append(u)

    # 每个 host 一个任务；任务内部串行抓取该 host 的所有 URL
    def _fetch_host(host_urls: list[str]) -> list[tuple[str, object, object]]:
        """抓取单个 host 下的所有 URL，返回 (url, kind, payload) 列表。

        kind: "jar" -> payload=(bytes, source) 或 Exception
              "text" -> payload=str 或 Exception
        """
        out: list[tuple[str, object, object]] = []
        for u in host_urls:
            # 每次抓取前检查截止时间，超时则放弃剩余 URL
            if time.monotonic() >= deadline:
                break
            atype = _asset_type(u)
            try:
                if atype == "jar":
                    # JAR 走 _fetch_jar（含候选回退 + 单候选优化）。
                    # 注意：_fetch_jar 第一个参数是 fetch_bytes 函数本身。
                    # 本函数是模块级，无法访问 run_scan 的局部变量 fetch_bytes，
                    # 因此直接引用 net.fetch_bytes。
                    # single_candidate 由主线程预读的集合决定（见上方注释）。
                    payload = _fetch_jar(
                        net.fetch_bytes,
                        u,
                        single_candidate=(u in single_candidate_urls),
                    )
                    out.append((u, "jar", payload))
                else:
                    # 文本抓取沿用原串行逻辑的默认超时（8s），
                    # 仅 JAR 使用缩短后的 JAR_FETCH_TIMEOUT_SECONDS。
                    # 同样直接引用 net.fetch_text（模块级函数无局部作用域）。
                    payload = net.fetch_text(u)
                    out.append((u, "text", payload))
            except Exception as exc:  # noqa: BLE001 - 失败也要回填缓存
                out.append((u, "jar" if atype == "jar" else "text", exc))
        return out

    # 并发执行：host 数可能远小于 URL 数，用 min 避免空转线程
    workers = max(1, min(SCAN_FETCH_WORKERS, len(by_host)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_fetch_host, host_urls) for host_urls in by_host.values()]
        for fut in as_completed(futures):
            try:
                results = fut.result()
            except Exception:  # noqa: BLE001 - 单个 host 失败不影响整体
                continue
            # 主线程统一回填缓存，避免 worker 并发写 dict
            for u, kind, payload in results:
                if kind == "jar":
                    binary_cache[u] = payload
                    # 方案E 统计修复：单候选路径实际触发次数。
                    # 原实现从未递增该字段，报告恒为 0，无法诊断优化是否生效。
                    if u in single_candidate_urls:
                        summary["jar_single_candidate_fetches"] += 1
                else:
                    text_cache[u] = payload


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
    # 扫描总预算从进入 run_scan 起算，给写库/出报告留出余量。
    scan_deadline_monotonic = time.monotonic() + SCAN_FETCH_DEADLINE_SECONDS
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
        "skipped_fetch_deadline": 0,
        "retained_prior_jar_results": 0,
        # 方案E：退避与候选递减统计，便于诊断预算去向
        "skipped_backoff_jar": 0,
        "skipped_backoff_text": 0,
        "jar_single_candidate_fetches": 0,
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

    # 方案A：并发预抓取。
    # 先收集本轮所有待抓取 URL（跳过模板 / 动态本地 API / 已在缓存中的），
    # 按 host 分组并发抓取，结果回填 binary_cache / text_cache。
    # 后续串行循环命中缓存后不再打网络，业务逻辑完全不变。
    if not jar_only:
        prefetch_urls: list[str] = []
        for _fp, _info in fps.items():
            for _u in sorted(_info["urls"]):
                if net.classify_url(_u) == "template":
                    continue
                if _is_dynamic_local_api(_u):
                    continue
                if _u in binary_cache or _u in text_cache:
                    continue
                # 关键：预抓取会填充 binary_cache/text_cache，使后续串行循环
                # 跳过冷却检查（`if url not in binary_cache`）。因此必须在此
                # 提前应用与串行循环完全一致的冷却/退避判定，否则会重复抓取
                # 本应跳过的 URL，破坏方案E 的退避语义。
                _atype = _asset_type(_u)
                _prior = _recent_url_fetch_status(con, _u, _atype)
                if _prior in ("failed", "fetched"):
                    continue
                prefetch_urls.append(_u)
        # 去重但保持稳定顺序
        prefetch_urls = list(dict.fromkeys(prefetch_urls))
        if prefetch_urls:
            _prefetch_concurrent(
                prefetch_urls,
                con=con,
                binary_cache=binary_cache,
                text_cache=text_cache,
                summary=summary,
                deadline=scan_deadline_monotonic,
            )

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
                        # 跨 fingerprint URL 冷却：任意指纹 24h 内成功/失败后都不再打网络。
                        # 本轮 binary_cache 仍优先，因此同一轮内后到的指纹会复用字节而非跳过。
                        prior_status = _recent_url_fetch_status(con, url, "jar")
                        if prior_status == "failed":
                            summary["skipped_recent_failed_jar"] += 1
                            # 方案E：区分「退避窗口内」与「普通冷却」
                            if _url_fail_count(con, url, "jar") >= 2:
                                summary["skipped_backoff_jar"] += 1
                            continue
                        if prior_status == "fetched":
                            summary["skipped_recent_fetched_jar"] += 1
                            continue
                        # 总预算用尽后停止新的网络请求；已有缓存/证据继续写报告。
                        if time.monotonic() >= scan_deadline_monotonic:
                            summary["skipped_fetch_deadline"] += 1
                            continue
                        try:
                            con.commit()  # 网络抓取前释放写锁
                            # 方案E：连续失败 >=2 次的死链只试首个候选，
                            # 避免 3 候选 × 超时 = 3 倍浪费。
                            fail_cnt = _url_fail_count(con, url, "jar")
                            binary_cache[url] = _fetch_jar(
                                fetch_bytes,
                                url,
                                single_candidate=(
                                    fail_cnt >= JAR_SINGLE_CANDIDATE_AFTER_FAILURES
                                ),
                            )
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
                        # 文本 URL 同样按 effective_url 跨指纹冷却，避免静态规则重复超时。
                        prior_text = _recent_url_fetch_status(con, url, atype)
                        if prior_text in ("fetched", "failed"):
                            summary["skipped_recent_text"] += 1
                            # 方案E：区分「退避窗口内」与「普通冷却」
                            if prior_text == "failed" and _url_fail_count(
                                con, url, atype
                            ) >= 2:
                                summary["skipped_backoff_text"] += 1
                            continue
                        if time.monotonic() >= scan_deadline_monotonic:
                            summary["skipped_fetch_deadline"] += 1
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
