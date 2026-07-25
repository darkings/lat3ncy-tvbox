#!/usr/bin/env python3
"""新源自动采集器：从 GitHub / 公开订阅地址抓取配置，去重并导入候选库。

对应 PLAN §三 新源获取方案。
- 从配置的订阅地址/仓库抓取最新配置 JSON
- 标准化与去重（依据 common.py 指纹）
- 新源写入 raw_source / norm_source，默认状态设为 candidate
- 记录采集报告至 reports/discovery-report.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import net
from common import assert_no_proxy, classify, compute_fingerprint

HERE = Path(__file__).resolve().parent

# 预设的公开活跃源订阅仓库/地址清单（可通过 CLI 或 config 自定义扩展）
DEFAULT_DISCOVERY_URLS = [
    "http://pandown.pro/tvbox/tvbox.json",
    "https://raw.liucn.cc/box/m.json",
    "https://agit.ai/Yoursmile7/TVBox/raw/branch/master/XC.json",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_subscription_config(url: str, *, fetch_fn=net.fetch_text, timeout: float = 10.0) -> dict | None:
    """抓取远程订阅 JSON 或读取本地文件并解析。"""
    try:
        if url.startswith("file://") or Path(url).exists():
            path = Path(url.replace("file://", ""))
            raw_text = path.read_text(encoding="utf-8")
        else:
            raw_text = fetch_fn(url, timeout=timeout)
        # 去除 BOM 字符
        raw_text = raw_text.lstrip("\ufeff")
        # 去除 C 语言风格单行/多行注释 // ...
        lines = []
        for line in raw_text.splitlines():
            s = line.strip()
            if s.startswith("//"):
                continue
            lines.append(line)
        clean_text = "\n".join(lines)
        data = json.loads(clean_text)
        if isinstance(data, dict) and "sites" in data:
            return data
    except Exception as e:
        print(f"[discovery-warning] {url} fetch/parse failed: {e}")
    return None


def discover_and_import(db_path: str, urls: list[str], policy_path: str,
                        batch_name: str, *, report_path: str | None = None,
                        fetch_fn=net.fetch_text, now: str | None = None) -> dict:
    """从给定的订阅 URL 列表中发现并导入新源。"""
    now = now or _now()
    policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))

    con = sqlite3.connect(str(db_path))

    # 获取已有的指纹集合
    existing_fps = set(
        r[0] for r in con.execute("SELECT fingerprint FROM norm_source").fetchall()
    )

    summary = {
        "urls_checked": len(urls),
        "urls_successful": 0,
        "raw_sites_found": 0,
        "new_candidates_added": 0,
        "duplicates_skipped": 0,
        "discovered_sources": [],
    }

    con.execute("BEGIN")
    try:
        for url in urls:
            config = fetch_subscription_config(url, fetch_fn=fetch_fn)
            if not config:
                continue

            summary["urls_successful"] += 1
            sites = config.get("sites", [])
            summary["raw_sites_found"] += len(sites)

            for site in sites:
                site_key = str(site.get("key", ""))
                site_name = site.get("name", "")
                fp, meta = compute_fingerprint(site)

                if fp in existing_fps:
                    summary["duplicates_skipped"] += 1
                    continue

                # 插入新 raw_source
                raw_json = json.dumps(site, ensure_ascii=False)
                cur = con.execute(
                    "INSERT OR IGNORE INTO raw_source"
                    "(import_batch, origin, site_key, name, type, api, ext, raw_json)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (batch_name, url, site_key, site_name, site.get("type"),
                     site.get("api") if isinstance(site.get("api"), str) else json.dumps(site.get("api")),
                     site.get("ext") if isinstance(site.get("ext"), str) else json.dumps(site.get("ext")),
                     raw_json)
                )
                if cur.rowcount == 0:
                    continue

                raw_id = cur.lastrowid
                category = classify(site_name, policy)

                # 插入 norm_source
                con.execute(
                    "INSERT INTO norm_source"
                    "(raw_id, fingerprint, api_host, required_urls, jar_md5, spider_class, category, capabilities)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (raw_id, fp, meta["api_host"], json.dumps(meta["required_urls"], ensure_ascii=False),
                     meta["jar_md5"], meta["spider_class"], category, json.dumps([], ensure_ascii=False))
                )

                # 设为 candidate 候选状态
                con.execute(
                    "INSERT OR IGNORE INTO list_state(fingerprint, state, reason, updated_at)"
                    " VALUES(?,?,?,?)",
                    (fp, "candidate", f"discovered_from:{url}", now)
                )

                existing_fps.add(fp)
                summary["new_candidates_added"] += 1
                summary["discovered_sources"].append({
                    "fingerprint": fp,
                    "name": site_name,
                    "category": category,
                    "origin": url,
                })

        con.commit()
    except Exception as e:
        con.rollback()
        con.close()
        raise e

    con.close()

    if report_path:
        report = {"summary": summary, "generated_at": now}
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(HERE / "data" / "sources.db"))
    p.add_argument("--policy", default=str(HERE / "config" / "policy.json"))
    p.add_argument("--urls-file", help="保存订阅 URL 的文本文件（每行一个）")
    p.add_argument("--batch", default=f"discovery-{datetime.now(timezone.utc).strftime('%Y%m%d')}")
    p.add_argument("--report", default=str(HERE / "reports" / "discovery-report.json"))
    args = p.parse_args()

    urls = DEFAULT_DISCOVERY_URLS
    if args.urls_file and Path(args.urls_file).exists():
        urls = [
            line.strip()
            for line in Path(args.urls_file).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    result = discover_and_import(args.db, urls, args.policy, args.batch, report_path=args.report)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
