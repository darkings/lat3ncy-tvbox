#!/usr/bin/env python3
"""无代理连通性探测 CLI：按指纹汇总 URL，分层探测并入库。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ponyo_source_manager.core import net
from ponyo_source_manager.core.common import PONYO_HOME as HERE
from ponyo_source_manager.core.common import assert_no_proxy, iri_to_uri

_TIMESLOTS = {
    (6, 11): "morning",
    (11, 15): "noon",
    (15, 21): "evening",
    (21, 24): "night",
    (0, 6): "night",
}

APPROVED_ASSET_BASE_URL = os.getenv(
    "APPROVED_ASSET_BASE_URL",
    "https://api.ponyo.fun/assets/jar",
).rstrip("/")
TRUSTED_DRPY_ASSET_PREFIXES = ("/js/", "/cat/", "/public/")


class _NoLocalRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("trusted drpy API redirects are forbidden")


def _is_trusted_drpy_api(url: str) -> bool:
    parts = urlsplit(url)
    return (
        parts.scheme == "http"
        and parts.hostname in {"127.0.0.1", "::1"}
        and parts.port == 5757
        and parts.path.startswith("/api/")
        and not parts.username
        and not parts.password
    )


def _is_trusted_drpy_asset(url: str) -> bool:
    """Allow only immutable runtime assets on the dedicated local DRPY port."""
    parts = urlsplit(url)
    return (
        parts.scheme == "http"
        and parts.hostname in {"127.0.0.1", "::1"}
        and parts.port == 5757
        and parts.path.startswith(TRUSTED_DRPY_ASSET_PREFIXES)
        and not parts.username
        and not parts.password
    )


def _probe_trusted_drpy(url: str, *, now: str) -> dict:
    if not _is_trusted_drpy_api(url):
        raise ValueError("not a trusted drpy API URL")
    started = time.monotonic()
    result = {
        "url": url,
        "checked_at": now,
        "dns_ok": 1,
        "tcp_ok": 1,
        "tls_ok": 1,
        "http_status": 0,
        "latency_ms": 0,
        "redirect_count": 0,
        "ok": 0,
        "err": None,
    }
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoLocalRedirect()
    )
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("wd", "测试")
    probe_url = iri_to_uri(
        urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
    )
    request = urllib.request.Request(
        probe_url, headers={"User-Agent": "ponyo-source-manager/1.0"}
    )
    try:
        with opener.open(request, timeout=10.0) as response:
            result["http_status"] = response.getcode()
            result["ok"] = int(200 <= response.getcode() < 400)
    except urllib.error.HTTPError as error:
        result["http_status"] = error.code
        result["err"] = f"http: {error.code}"
    except Exception as error:
        result["err"] = f"tcp: {error}"
    result["latency_ms"] = int((time.monotonic() - started) * 1000)
    return result


def _probe_trusted_drpy_asset(url: str, *, now: str) -> dict:
    """Fetch an allowlisted local runtime asset without proxy or redirects."""
    if not _is_trusted_drpy_asset(url):
        raise ValueError("not trusted drpy asset URL")
    started = time.monotonic()
    result = {
        "url": url,
        "checked_at": now,
        "dns_ok": 1,
        "tcp_ok": 1,
        "tls_ok": 1,
        "http_status": 0,
        "latency_ms": 0,
        "redirect_count": 0,
        "ok": 0,
        "err": None,
    }
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoLocalRedirect(),
    )
    request = urllib.request.Request(
        iri_to_uri(url),
        headers={"User-Agent": "ponyo-source-manager/1.0"},
    )
    try:
        with opener.open(request, timeout=10.0) as response:
            result["http_status"] = response.getcode()
            response.read(1)
            result["ok"] = int(200 <= response.getcode() < 400)
    except urllib.error.HTTPError as error:
        result["http_status"] = error.code
        result["err"] = f"http: {error.code}"
    except Exception as error:
        result["err"] = f"local-asset: {type(error).__name__}: {str(error)[:160]}"
    result["latency_ms"] = int((time.monotonic() - started) * 1000)
    return result


def current_timeslot() -> str:
    hour = datetime.now().hour
    for (lo, hi), name in _TIMESLOTS.items():
        if lo <= hour < hi:
            return name
    return "night"


def _approved_jar_rewrites(
    con: sqlite3.Connection,
    *,
    now: str,
    base_url: str = APPROVED_ASSET_BASE_URL,
) -> dict[tuple[str, str], str]:
    """Map approved upstream JAR references to their user-facing hosted URL."""
    try:
        rows = con.execute(
            "SELECT e.fingerprint,e.effective_url,lower(e.content_sha256) "
            "FROM dependency_asset_evidence e "
            "JOIN dependency_asset_approval a "
            "ON lower(a.content_sha256)=lower(e.content_sha256) "
            "WHERE e.asset_type='jar' AND e.effective_url<>'' "
            "AND a.asset_type='jar' AND a.status='approved' "
            "AND a.expires_at IS NOT NULL AND a.expires_at>?",
            (now,),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {
        (fingerprint, effective_url): f"{base_url.rstrip('/')}/{content_sha256}.jar"
        for fingerprint, effective_url, content_sha256 in rows
        if content_sha256
    }


def _group_urls(
    con: sqlite3.Connection,
    *,
    now: str,
    approved_asset_base_url: str = APPROVED_ASSET_BASE_URL,
) -> dict[str, set[str]]:
    """按指纹汇总所有需要探测的 URL。"""
    rows = con.execute("SELECT fingerprint, required_urls FROM norm_source").fetchall()
    approved_rewrites = _approved_jar_rewrites(
        con,
        now=now,
        base_url=approved_asset_base_url,
    )
    groups: dict[str, set[str]] = defaultdict(set)
    for fp, req in rows:
        for url in json.loads(req or "[]"):
            if net.classify_url(url) != "probe":
                continue
            rewritten = approved_rewrites.get((fp, url), url)
            # 已物化的 jar 资产由 materialize_approved_assets 每轮校验（cached+sha），
            # 无需网络探测；探测失败反而会拖累源的多时段稳定性（曾见 7 天窗口内
            # 一次资产 URL 失败使 stability 掉到 0.65）。
            if rewritten.startswith(APPROVED_ASSET_BASE_URL + "/"):
                continue
            groups[fp].add(rewritten)
    return groups


def run_probe(
    db_path,
    *,
    timeslot=None,
    report_path=None,
    probe_fn=net.probe,
    now=None,
    max_per_host=8,
    inter_host_delay=0.2,
    fingerprints=None,
    max_age_hours: float = 24.0,
    fail_cool_hours: float = 12.0,
) -> dict:
    """对所有指纹的远程 URL 做无代理连通性探测，结果写入 conn_probe 表。

    增量窗口（避免每轮全量串行探测 2588 URL 约 4 小时拖垮 cron 链）：

    - ``max_age_hours``：该窗口内探测成功（ok=1）的 URL 跳过本轮。
    - ``fail_cool_hours``：该窗口内探测失败（ok=0）的 URL 也跳过（失败冷却），
      防止每轮重复重试全部失败 URL（实测一轮约 1000+ 失败，每个 8s 超时）。
      12h 冷却后自动重试，源恢复检测延迟可接受。

    窗口为 0 时对应部分退化为全量探测。
    """
    if assert_no_proxy():
        raise SystemExit("代理环境变量非空，连通性探测中止（需无代理）。")

    now = now or datetime.now(timezone.utc).isoformat()
    timeslot = timeslot or current_timeslot()
    # timeout 是 sqlite busy timeout：探测耗时长，写入时可能与其他阶段进程
    # （dedupe/maccms_media/scan_security）短暂争锁，默认 5s 会直接 locked 崩溃。
    con = sqlite3.connect(str(db_path), timeout=60)

    groups = _group_urls(con, now=now)
    if fingerprints:
        selected = set(fingerprints)
        groups = {
            fingerprint: urls
            for fingerprint, urls in groups.items()
            if fingerprint in selected
        }
    all_urls: set[str] = set()
    for urls in groups.values():
        all_urls.update(urls)

    # 增量窗口：成功与失败都按各自冷却窗口跳过，新增/过期 URL 仍探测
    skip_ok_urls: set[str] = set()
    skip_fail_urls: set[str] = set()
    rotated_reprobe: set[str] = set()
    if max_age_hours and max_age_hours > 0:
        skip_rows = con.execute(
            "SELECT DISTINCT target_url FROM conn_probe "
            "WHERE ok=1 AND probed_at >= datetime('now', ?)",
            (f"-{max_age_hours} hours",),
        ).fetchall()
        recent_ok = {r[0] for r in skip_rows} & all_urls
        # 时段轮转：冷却窗口内成功的 URL 按 hash 分片，每轮重测 1/4。
        # 否则每个 URL 永远只在首次探测的时段留下记录，凑不齐 4 时段门禁。
        slot_index = {"morning": 0, "noon": 1, "evening": 2, "night": 3}.get(
            timeslot, 0
        )
        for url in recent_ok:
            if int(hashlib.md5(url.encode("utf-8")).hexdigest(), 16) % 4 == slot_index:
                rotated_reprobe.add(url)
            else:
                skip_ok_urls.add(url)
    if fail_cool_hours and fail_cool_hours > 0:
        fail_rows = con.execute(
            "SELECT DISTINCT target_url FROM conn_probe "
            "WHERE ok=0 AND probed_at >= datetime('now', ?)",
            (f"-{fail_cool_hours} hours",),
        ).fetchall()
        skip_fail_urls = {r[0] for r in fail_rows} & all_urls
    skip_urls = (skip_ok_urls | skip_fail_urls) - rotated_reprobe

    # 按 host 分组，同 host 串行 + 间隔
    from urllib.parse import urlsplit

    host_urls: dict[str, list[str]] = defaultdict(list)
    for url in sorted(all_urls - skip_urls):
        host = urlsplit(url).hostname or ""
        host_urls[host].append(url)

    results: dict[str, dict] = {}
    rows_written = 0
    written_urls: set[str] = set()

    def _probe_host(host: str, urls: list[str]) -> dict[str, dict]:
        """探测单个 host 下的全部 URL（host 内串行，防目标限流）。"""
        local: dict[str, dict] = {}
        for url in urls:
            try:
                if probe_fn is net.probe and _is_trusted_drpy_api(url):
                    local[url] = _probe_trusted_drpy(url, now=now)
                elif probe_fn is net.probe and _is_trusted_drpy_asset(url):
                    local[url] = _probe_trusted_drpy_asset(url, now=now)
                else:
                    local[url] = probe_fn(url, now=now)
            except Exception as exc:
                # 单个 URL 探测异常不中断整轮；其余 URL 继续，避免重蹈 DNS 超时崩溃。
                local[url] = {
                    "dns_ok": 0,
                    "tcp_ok": 0,
                    "tls_ok": None,
                    "http_status": None,
                    "latency_ms": None,
                    "ok": 0,
                    "err": f"{type(exc).__name__}: {str(exc)[:120]}",
                    "probed_at": now,
                }
            if inter_host_delay > 0:
                time.sleep(inter_host_delay)
        return local

    def _persist_host(host_urls_sub: list[str]) -> None:
        """把该 host 已探测的结果落库（并发环境下由主线程统一调用）。"""
        nonlocal rows_written
        for fp, fp_urls in groups.items():
            for url in sorted(fp_urls):
                if url not in results or url in written_urls:
                    continue
                written_urls.add(url)
                r = results[url]
                con.execute(
                    "INSERT INTO conn_probe"
                    "(fingerprint,target_url,timeslot,dns_ok,tcp_ok,tls_ok,"
                    "http_status,latency_ms,ok,err,probed_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        fp,
                        url,
                        timeslot,
                        r["dns_ok"],
                        r["tcp_ok"],
                        r["tls_ok"],
                        r["http_status"],
                        r["latency_ms"],
                        r["ok"],
                        r["err"],
                        now,
                    ),
                )
                rows_written += 1
        con.commit()

    # host 间并发（同 host 内保持串行）：URL 集膨胀后串行全量探测需 2-3h，
    # 并发可将单轮压缩到分钟级。写库由主线程串行执行，避免 sqlite 并发写冲突。
    from concurrent.futures import ThreadPoolExecutor, as_completed

    host_items = list(host_urls.items())
    with ThreadPoolExecutor(max_workers=16) as ex:
        futures = {
            ex.submit(_probe_host, host, urls): host for host, urls in host_items
        }
        for fut in as_completed(futures):
            host = futures[fut]
            try:
                results.update(fut.result())
            except Exception:
                pass
            # 该 host 探测完立即落库：阶段被看门狗超时杀掉时，已探数据不丢失。
            _persist_host(host_urls[host])

    # 兜底：写入循环中未覆盖的结果（分组与探测集不一致时的残余）
    for fp, urls in groups.items():
        for url in sorted(urls):
            r = results.get(url)
            if not r or url in written_urls:
                continue
            written_urls.add(url)
            con.execute(
                "INSERT INTO conn_probe"
                "(fingerprint,target_url,timeslot,dns_ok,tcp_ok,tls_ok,"
                "http_status,latency_ms,ok,err,probed_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    fp,
                    url,
                    timeslot,
                    r["dns_ok"],
                    r["tcp_ok"],
                    r["tls_ok"],
                    r["http_status"],
                    r["latency_ms"],
                    r["ok"],
                    r["err"],
                    now,
                ),
            )
            rows_written += 1
    con.commit()

    # 汇总
    total = len(all_urls)
    ok = sum(1 for r in results.values() if r["ok"])
    fail = len(results) - ok
    summary = {
        "timeslot": timeslot,
        "total_urls": total,
        "probed": len(results),
        "skipped_recent_ok": len(skip_ok_urls),
        "skipped_recent_fail": len(skip_fail_urls),
        "rotated_reprobe": len(rotated_reprobe),
        "ok": ok,
        "fail": fail,
        "rows_written": rows_written,
        "fingerprints": len(groups),
    }

    if report_path:
        report = {
            "summary": summary,
            "generated_at": now,
            "probes": [{"url": url, **r} for url, r in sorted(results.items())],
        }
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    con.close()
    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(HERE / "data" / "sources.db"))
    p.add_argument(
        "--timeslot", default=None, help="morning|noon|evening|night (default: auto)"
    )
    p.add_argument(
        "--report", default=str(HERE / "reports" / "connectivity-report.json")
    )
    p.add_argument(
        "--fingerprint",
        action="append",
        default=None,
        help="probe only this fingerprint (repeatable)",
    )
    p.add_argument(
        "--max-age-hours",
        type=float,
        default=24.0,
        help="skip URLs probed OK within this window (0 = full probe)",
    )
    p.add_argument(
        "--fail-cool-hours",
        type=float,
        default=12.0,
        help="skip URLs that failed within this window (0 = always retry)",
    )
    args = p.parse_args()
    result = run_probe(
        args.db,
        timeslot=args.timeslot,
        report_path=args.report,
        fingerprints=args.fingerprint,
        max_age_hours=args.max_age_hours,
        fail_cool_hours=args.fail_cool_hours,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
