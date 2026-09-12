#!/usr/bin/env python3
"""重算当前 allow 源的分类并产出审计报告（不发布、不修改订阅）。

面向“源会晋级、分类会变动”的运行环境：
- 每次运行读取当前 list_state/dedup_group/raw_source 快照；
- 按统一字典归一化分类，记录 whitelist/declared/none 三种来源；
- 聚合未识别分类名为待维护别名（pending_aliases）；
- 与上一份报告做 diff，输出新增/移除/分类漂移；
- 输出 reports/category-report.json。
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ponyo_source_manager.core.common import DATA_DIR, REPORT_DIR
from ponyo_source_manager.publishing.category_taxonomy import (
    load_host_whitelist,
    load_taxonomy,
    normalize_categories,
    raw_signature,
)


def _host_of(api: str) -> str | None:
    import re

    m = re.search(r"https?://([^/]+)", api or "")
    return m.group(1).lower().removeprefix("www.") if m else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _infer_categories(name: str, api: str, tx: dict) -> list[str]:
    n = (name or "").lower()
    if any(k in n for k in ("[听]", "音乐", "dj", "mv")):
        return ["其他"]
    if str(api or "").startswith("http"):
        return list(tx.get("default_categories", []))
    return []


def recompute(db_path: str | Path, *, probe: bool = False, probe_all: bool = False) -> dict:
    tx = load_taxonomy()
    whitelist = load_host_whitelist()
    cache_path = Path(DATA_DIR) / "category-cache.json"
    try:
        category_cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        category_cache = {}
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        WITH LatestScores AS (
            SELECT fingerprint, total_score,
                   ROW_NUMBER() OVER(PARTITION BY fingerprint ORDER BY scored_at DESC) as rn
            FROM score_snapshot
        )
        SELECT r.raw_json, s.total_score, dg.fingerprint
        FROM list_state ls
        JOIN dedup_group dg ON ls.fingerprint = dg.fingerprint
        JOIN raw_source r ON dg.primary_raw_id = r.id
        LEFT JOIN LatestScores s ON ls.fingerprint = s.fingerprint AND s.rn = 1
        WHERE ls.state = 'allow'
        ORDER BY COALESCE(s.total_score, 0) DESC
        """
    ).fetchall()
    con.close()

    sources: list[dict] = []
    cache_dirty = False
    for row in rows:
        try:
            site = json.loads(row["raw_json"])
        except Exception:
            continue
        api = str(site.get("api", "") or "")
        host = _host_of(api)
        raw_classes: list = site.get("class") or []
        cached_raw: list = category_cache.get(api) or []
        if not raw_classes and cached_raw:
            raw_classes = cached_raw
            provenance = "cache"
        elif raw_classes:
            provenance = "declared"
        else:
            provenance = "none"
        wl_host = None
        for key in whitelist:
            if host and host.endswith(key):
                wl_host = key
                break
        if wl_host:
            result = normalize_categories(whitelist[wl_host], tx)
            provenance = "whitelist"
        else:
            live = None
            if probe or probe_all:
                from ponyo_source_manager.publishing.generate_subscription import (
                    _detect_top_categories,
                )

                live = _detect_top_categories(api)
            if live:
                result = normalize_categories(live, tx)
                provenance = "detected" if result.categories else "none"
                category_cache[api] = {
                    "sig": raw_signature(live),
                    "at": _now(),
                    "cats": list(live),
                }
                cache_dirty = True
            elif raw_classes:
                result = normalize_categories(raw_classes, tx)
                if not result.categories:
                    provenance = "none"
            else:
                result = normalize_categories([], tx)
                provenance = "none"
        if not result.categories and provenance == "none":
            inferred = _infer_categories(str(site.get("name", "") or ""), api, tx)
            if inferred:
                result = normalize_categories(inferred, tx)
                provenance = "inferred"
        sources.append(
            {
                "name": str(site.get("name", "") or ""),
                "host": host,
                "fingerprint": str(row["fingerprint"]),
                "score": row["total_score"],
                "raw": [
                    str(c.get("type_name") if isinstance(c, dict) else c).strip()
                    for c in raw_classes
                    if isinstance(c, (str, dict))
                ],
                "categories": result.categories,
                "provenance": provenance,
                "unmapped": result.unmapped,
                "denied": result.denied,
            }
        )

    unmapped_counter: dict[str, int] = {}
    denied_counter: dict[str, int] = {}
    for s in sources:
        for name in s["unmapped"]:
            unmapped_counter[name] = unmapped_counter.get(name, 0) + 1
        for name in s["denied"]:
            denied_counter[name] = denied_counter.get(name, 0) + 1

    report = {
        "generated_at": _now(),
        "taxonomy_version": tx.get("version"),
        "summary": {
            "total": len(sources),
            "with_categories": sum(1 for s in sources if s["categories"]),
            "none": sum(1 for s in sources if s["provenance"] == "none"),
            "by_provenance": {
                p: sum(1 for s in sources if s["provenance"] == p)
                for p in (
                    "whitelist", "declared", "cache", "detected",
                    "inferred", "none",
                )
            },
        },
        "pending_aliases": dict(
            sorted(unmapped_counter.items(), key=lambda kv: -kv[1])
        ),
        "denied_names": dict(sorted(denied_counter.items(), key=lambda kv: -kv[1])),
        "sources": sources,
    }

    report_path = Path(REPORT_DIR) / "category-report.json"
    previous = None
    if report_path.exists():
        try:
            previous = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            previous = None
    if previous and isinstance(previous.get("sources"), list):
        prev_fps = {s.get("fingerprint") for s in previous["sources"]}
        cur_fps = {s["fingerprint"] for s in sources}
        prev_cats = {s.get("fingerprint"): s.get("categories") for s in previous["sources"]}
        changed = []
        for s in sources:
            if s["fingerprint"] in prev_cats and prev_cats[s["fingerprint"]] != s["categories"]:
                changed.append(
                    {
                        "name": s["name"],
                        "fingerprint": s["fingerprint"],
                        "before": prev_cats[s["fingerprint"]],
                        "after": s["categories"],
                    }
                )
        report["diff"] = {
            "added": sorted(cur_fps - prev_fps),
            "removed": sorted(prev_fps - cur_fps),
            "category_changed": changed,
        }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if cache_dirty:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(category_cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        default=str(Path(DATA_DIR) / "sources.db"),
        help="sources.db 路径",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="对无声明/无缓存分类的源执行实时 ac=list 探测",
    )
    parser.add_argument(
        "--probe-all",
        action="store_true",
        help="对全部 http 源实时探测，覆盖缓存结果",
    )
    args = parser.parse_args()
    report = recompute(args.db, probe=args.probe, probe_all=args.probe_all)
    print(json.dumps(report["summary"], ensure_ascii=False))
    print("pending_aliases:", json.dumps(report["pending_aliases"], ensure_ascii=False))
    print("report written")


if __name__ == "__main__":
    main()
