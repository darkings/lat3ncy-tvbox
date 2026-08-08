#!/usr/bin/env python3
"""Persist traceable source categories and capability sampling evidence.

Classification never promotes, denies, or scores a source.  Declared metadata
and observed successful searches are recorded separately so downstream
aggregators can require both a capability and the existing hard-pass gates.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from ponyo_source_manager.core.common import CONFIG_DIR, DATA_DIR, REPORT_DIR
from ponyo_source_manager.discovery.audit_types import audit_source


CLASSIFIER_VERSION = "capability-v1"
ROLE_CAPABILITIES = {
    "children": "children",
    "cloud_drive": "cloud_drive",
    "local": "local",
    "live": "live",
    "settings": "settings",
    "tool": "tool",
}
CATEGORY_CAPABILITIES = {
    "儿童": "children",
    "动漫": "anime",
    "纪录": "documentary",
    "综艺": "variety",
    "网盘": "cloud_drive",
    "直播": "live",
}
ROLE_CATEGORIES = {
    "live": "直播",
    "cloud_drive": "网盘",
    "local": "工具",
    "settings": "工具",
    "tool": "工具",
    "children": "儿童",
}
CATEGORY_PRIORITY = {
    category: priority
    for priority, category in enumerate(
        ("工具", "直播", "网盘", "儿童", "动漫", "纪录", "综艺", "影视", "未分类")
    )
}
PROFILE_CAPABILITIES = {
    "children": "children",
    "animation": "anime",
    "short_drama": "short_drama",
    "books_audio": "books_audio",
    "audio_music": "audio_music",
    "documentary": "documentary",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _keyword_capabilities(path: str | Path) -> dict[str, str]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    profiles = document.get("profiles", document)
    result: dict[str, str] = {}
    for profile, keywords in profiles.items():
        capability = PROFILE_CAPABILITIES.get(str(profile))
        for keyword in keywords if isinstance(keywords, list) else []:
            keyword = str(keyword).strip()
            if not keyword:
                continue
            if profile == "general":
                capability = "movie" if keyword == "流浪地球" else "tv"
            if capability:
                result[keyword] = capability
    return result


def _primary_category(current: str, audited: dict) -> str:
    roles = list(audited.get("content_roles") or [])
    for role in roles:
        if role in ROLE_CATEGORIES:
            return ROLE_CATEGORIES[role]
    return current or "未分类"


def _declared_evidence(rows: list[sqlite3.Row]) -> tuple[dict, dict]:
    categories: dict[str, str] = {}
    evidence: dict[str, dict[str, list[dict]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        source = dict(row)
        audited = audit_source(source)
        fp = str(row["fingerprint"])
        category = _primary_category(str(row["category"] or "未分类"), audited)
        existing = categories.get(fp)
        if existing is None or CATEGORY_PRIORITY.get(
            category, 999
        ) < CATEGORY_PRIORITY.get(existing, 999):
            categories[fp] = category

        capabilities = {
            ROLE_CAPABILITIES[role]
            for role in audited.get("content_roles") or []
            if role in ROLE_CAPABILITIES
        }
        category_capability = CATEGORY_CAPABILITIES.get(category)
        if category_capability:
            capabilities.add(category_capability)
        for capability in capabilities:
            evidence[fp][capability].append(
                {
                    "kind": "declared",
                    "raw_id": row["id"],
                    "name": audited.get("name"),
                    "roles": audited.get("content_roles", []),
                    "runtime": audited.get("runtime_type"),
                }
            )
    return categories, evidence


def _observed_evidence(
    con: sqlite3.Connection,
    keyword_map: dict[str, str],
    *,
    days: int,
) -> dict[str, dict[str, list[dict]]]:
    rows = con.execute(
        "SELECT d.id,d.fingerprint,COALESCE(d.keyword,''),d.result_count,"
        "COALESCE(d.run_id,''),COALESCE(d.adapter_version,''),d.tested_at,"
        "r.run_id,r.finished_at "
        "FROM drpy_test_result d LEFT JOIN drpy_run r ON r.run_id=d.run_id "
        "WHERE d.test_type='search' AND d.success=1 "
        "AND COALESCE(d.result_count,0)>0 "
        "AND d.tested_at >= datetime('now', ?) ORDER BY d.tested_at,d.id",
        (f"-{days} days",),
    ).fetchall()
    canonical: dict[tuple[str, str, str, str], sqlite3.Row] = {}
    for row in rows:
        keyword = str(row[2])
        if keyword not in keyword_map:
            continue
        connector_run = str(row[4] or "")
        known_drpy_run = row[7] is not None
        if known_drpy_run and not row[8]:
            continue
        logical_run = connector_run or f"legacy:{row[0]}"
        key = (str(row[1]), logical_run, keyword, str(row[5] or ""))
        canonical[key] = row

    evidence: dict[str, dict[str, list[dict]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in canonical.values():
        fp = str(row[1])
        keyword = str(row[2])
        capability = keyword_map[keyword]
        evidence[fp][capability].append(
            {
                "kind": "observed_search",
                "keyword": keyword,
                "result_count": int(row[3] or 0),
                "run_id": str(row[4] or f"legacy:{row[0]}"),
                "adapter": str(row[5] or "legacy"),
                "tested_at": row[6],
            }
        )
    return evidence


def classify_capabilities(
    db_path: str | Path,
    *,
    keywords_path: str | Path = CONFIG_DIR / "test_keywords.json",
    report_path: str | Path | None = None,
    days: int = 7,
    now: str | None = None,
) -> dict:
    now = now or _now()
    keyword_map = _keyword_capabilities(keywords_path)
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    source_rows = con.execute(
        "SELECT r.id,r.origin,r.site_key,r.name,r.type,r.api,r.ext,r.raw_json,"
        "n.fingerprint,n.category FROM raw_source r "
        "JOIN norm_source n ON n.raw_id=r.id"
    ).fetchall()
    categories, declared = _declared_evidence(source_rows)
    observed = _observed_evidence(con, keyword_map, days=days)

    fingerprints = sorted({str(row["fingerprint"]) for row in source_rows})
    capability_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    details: list[dict] = []
    con.execute("BEGIN")
    try:
        con.execute("DELETE FROM capability_sampling")
        for fp in fingerprints:
            combined: dict[str, list[dict]] = defaultdict(list)
            for capability, items in declared.get(fp, {}).items():
                combined[capability].extend(items)
            for capability, items in observed.get(fp, {}).items():
                combined[capability].extend(items)

            capabilities = sorted(combined)
            category = categories.get(fp, "未分类")
            old_rows = con.execute(
                "SELECT DISTINCT category,capabilities FROM norm_source "
                "WHERE fingerprint=?",
                (fp,),
            ).fetchall()
            old_value = sorted(
                (dict(row) for row in old_rows),
                key=lambda item: (str(item["category"]), str(item["capabilities"])),
            )
            new_capabilities = json.dumps(capabilities, ensure_ascii=False)
            con.execute(
                "UPDATE norm_source SET category=?,capabilities=? "
                "WHERE fingerprint=?",
                (category, new_capabilities, fp),
            )

            for capability, items in combined.items():
                observed_hits = sum(
                    int(item.get("result_count", 0))
                    for item in items
                    if item.get("kind") == "observed_search"
                )
                hit_count = observed_hits or len(items)
                evidence_json = json.dumps(
                    {
                        "classifier_version": CLASSIFIER_VERSION,
                        "items": items[:50],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                con.execute(
                    "INSERT INTO capability_sampling"
                    "(fingerprint,capability,hit_count,sampling_evidence,verified_at) "
                    "VALUES(?,?,?,?,?)",
                    (fp, capability, hit_count, evidence_json, now),
                )
                capability_counts[capability] += 1

            new_value = {"category": category, "capabilities": capabilities}
            expected_old_shape = [
                {"category": category, "capabilities": new_capabilities}
            ]
            if old_value != expected_old_shape:
                con.execute(
                    "INSERT INTO audit_log"
                    "(entity_type,entity_id,action,old_value,new_value,reason,acted_at) "
                    "VALUES('source',?,'capability_refresh',?,?,?,?)",
                    (
                        fp,
                        json.dumps(old_value, ensure_ascii=False, sort_keys=True),
                        json.dumps(new_value, ensure_ascii=False, sort_keys=True),
                        CLASSIFIER_VERSION,
                        now,
                    ),
                )
            category_counts[category] += 1
            details.append(
                {
                    "fingerprint": fp,
                    "category": category,
                    "capabilities": capabilities,
                    "declared": sorted(declared.get(fp, {})),
                    "observed": sorted(observed.get(fp, {})),
                }
            )
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    summary = {
        "classifier_version": CLASSIFIER_VERSION,
        "sources": len(fingerprints),
        "categories": dict(sorted(category_counts.items())),
        "capabilities": dict(sorted(capability_counts.items())),
        "declared_sources": sum(bool(declared.get(fp)) for fp in fingerprints),
        "observed_sources": sum(bool(observed.get(fp)) for fp in fingerprints),
        "children_capable": capability_counts.get("children", 0),
    }
    if report_path:
        report = {"summary": summary, "generated_at": now, "sources": details}
        target = Path(report_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="持久化内容分类与能力抽样证据")
    parser.add_argument("--db", default=str(DATA_DIR / "sources.db"))
    parser.add_argument("--keywords", default=str(CONFIG_DIR / "test_keywords.json"))
    parser.add_argument(
        "--report", default=str(REPORT_DIR / "capability-report.json")
    )
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    result = classify_capabilities(
        args.db,
        keywords_path=args.keywords,
        report_path=args.report,
        days=args.days,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
