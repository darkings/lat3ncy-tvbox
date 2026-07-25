#!/usr/bin/env python3
"""无代理连通性探测 CLI：按指纹汇总 URL，分层探测并入库。"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import net
from common import assert_no_proxy

HERE = Path(__file__).resolve().parent

_TIMESLOTS = {
    (6, 11): "morning",
    (11, 15): "noon",
    (15, 21): "evening",
    (21, 24): "night",
    (0, 6): "night",
}


def current_timeslot() -> str:
    hour = datetime.now().hour
    for (lo, hi), name in _TIMESLOTS.items():
        if lo <= hour < hi:
            return name
    return "night"


def _group_urls(con: sqlite3.Connection) -> dict[str, set[str]]:
    """按指纹汇总所有需要探测的 URL。"""
    rows = con.execute(
        "SELECT fingerprint, required_urls FROM norm_source"
    ).fetchall()
    groups: dict[str, set[str]] = defaultdict(set)
    for fp, req in rows:
        for url in json.loads(req or "[]"):
            if net.classify_url(url) == "probe":
                groups[fp].add(url)
    return groups


def run_probe(db_path, *, timeslot=None, report_path=None,
              probe_fn=net.probe, now=None, max_per_host=8,
              inter_host_delay=0.2) -> dict:
    """对所有指纹的远程 URL 做无代理连通性探测，结果写入 conn_probe 表。"""
    if assert_no_proxy():
        raise SystemExit("代理环境变量非空，连通性探测中止（需无代理）。")

    now = now or datetime.now(timezone.utc).isoformat()
    timeslot = timeslot or current_timeslot()
    con = sqlite3.connect(str(db_path))

    groups = _group_urls(con)
    all_urls: set[str] = set()
    for urls in groups.values():
        all_urls.update(urls)

    # 按 host 分组，同 host 串行 + 间隔
    from urllib.parse import urlsplit
    host_urls: dict[str, list[str]] = defaultdict(list)
    for url in sorted(all_urls):
        host = urlsplit(url).hostname or ""
        host_urls[host].append(url)

    results: dict[str, dict] = {}
    for host, urls in host_urls.items():
        for url in urls:
            results[url] = probe_fn(url, now=now)
            if inter_host_delay > 0:
                time.sleep(inter_host_delay)

    # 按指纹汇总写入 conn_probe
    rows_written = 0
    for fp, urls in groups.items():
        for url in sorted(urls):
            r = results.get(url)
            if not r:
                continue
            con.execute(
                "INSERT INTO conn_probe"
                "(fingerprint,target_url,timeslot,dns_ok,tcp_ok,tls_ok,"
                "http_status,latency_ms,ok,err,probed_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (fp, url, timeslot, r["dns_ok"], r["tcp_ok"], r["tls_ok"],
                 r["http_status"], r["latency_ms"], r["ok"], r["err"], now))
            rows_written += 1
    con.commit()

    # 汇总
    total = len(all_urls)
    ok = sum(1 for r in results.values() if r["ok"])
    fail = total - ok
    summary = {
        "timeslot": timeslot, "total_urls": total,
        "ok": ok, "fail": fail, "rows_written": rows_written,
        "fingerprints": len(groups),
    }

    if report_path:
        report = {
            "summary": summary, "generated_at": now,
            "probes": [
                {"url": url, **r}
                for url, r in sorted(results.items())
            ],
        }
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    con.close()
    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(HERE / "data" / "sources.db"))
    p.add_argument("--timeslot", default=None,
                   help="morning|noon|evening|night (default: auto)")
    p.add_argument("--report", default=str(HERE / "reports" / "connectivity-report.json"))
    args = p.parse_args()
    result = run_probe(args.db, timeslot=args.timeslot, report_path=args.report)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
