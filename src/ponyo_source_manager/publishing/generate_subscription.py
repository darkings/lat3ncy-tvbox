#!/usr/bin/env python3
"""生成订阅文件与裁决精选 30 入口。

对应 PLAN §十七 与 §十八。
输出文件：
- subscription/ponyo-lite.json (精选 30 + 工具)
- subscription/ponyo-full.json (全量候选)
- subscription/ponyo-live.json (唯一正式直播源)
- subscription/ponyo-children.json (儿童聚合源)
- subscription/manifest.json (版本/哈希/清单)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ponyo_source_manager.core.common import DATA_DIR, CODE_DIR, PONYO_ROOT
PROJECT_ROOT = PONYO_ROOT
SUB_DIR = PROJECT_ROOT / "subscription"
APPROVED_ASSET_BASE_URL = os.getenv(
    "APPROVED_ASSET_BASE_URL",
    "https://api.ponyo.fun/assets/jar",
).rstrip("/")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _calc_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _load_approved_jar_urls(
    con: sqlite3.Connection,
    *,
    now: str,
    base_url: str = APPROVED_ASSET_BASE_URL,
) -> dict[str, str]:
    """Map source fingerprints to immutable, currently approved JAR URLs."""
    rows = con.execute(
        "SELECT d.fingerprint,d.content_sha256,d.actual_md5,d.source_field "
        "FROM dependency_asset_evidence d "
        "JOIN dependency_asset_approval a "
        "ON lower(a.content_sha256)=lower(d.content_sha256) "
        "WHERE d.asset_type='jar' AND d.content_sha256 IS NOT NULL "
        "AND a.asset_type='jar' AND a.status='approved' "
        "AND a.expires_at IS NOT NULL AND a.expires_at>? "
        "ORDER BY d.fingerprint, CASE d.source_field "
        "WHEN 'site.jar' THEN 0 WHEN 'config.jar' THEN 1 "
        "WHEN 'config.spider' THEN 2 ELSE 3 END",
        (now,),
    ).fetchall()
    result: dict[str, str] = {}
    for row in rows:
        fingerprint = row["fingerprint"]
        if fingerprint in result:
            continue
        sha256 = row["content_sha256"].lower()
        url = f"{base_url.rstrip('/')}/{sha256}.jar"
        actual_md5 = (row["actual_md5"] or "").lower()
        if actual_md5:
            url = f"{url};md5;{actual_md5}"
        result[fingerprint] = url
    return result


def _attach_approved_jar(
    site: dict,
    fingerprint: str,
    approved_jar_urls: dict[str, str],
) -> dict:
    approved_url = approved_jar_urls.get(fingerprint)
    if not approved_url:
        return site
    rewritten = dict(site)
    rewritten["jar"] = approved_url
    return rewritten


def generate_all_subscriptions(db_path: str, *, output_dir: str | Path | None = None,
                               now: str | None = None) -> dict:
    now = now or _now()
    out_path = Path(output_dir) if output_dir else SUB_DIR
    out_path.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    approved_jar_urls = _load_approved_jar_urls(con, now=now)

    from ponyo_source_manager.publishing import children_aggregate
    from ponyo_source_manager.probes import live as live_manager

    # 1. 精选 29 源提取 (按评分排序取前29，且指纹互异)
    rows_allow = con.execute("""
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
        LIMIT 29
    """).fetchall()

    vod_sites = []
    for r in rows_allow:
        try:
            site_obj = json.loads(r["raw_json"])
            vod_sites.append(
                _attach_approved_jar(site_obj, r["fingerprint"], approved_jar_urls)
            )
        except Exception:
            pass
            
    # 获取儿童聚合源 (1 个)
    children_res = children_aggregate.aggregate_children_sources(db_path, now=now)
    children_site = children_res.get("tvbox_site")
    
    # 29 个精选点播源 + 1 个儿童聚合源 = 30 个计数源
    counted_sites = []
    if children_site:
        counted_sites.append(children_site)
    counted_sites.extend(vod_sites)
        
    # 获取唯一正式直播源
    live_res = live_manager.select_official_live_source(db_path, now=now)
    official_live_key = live_res.get("official_key")

    # 2. 读取基础配置模板（如豆瓣推荐、设置、本地播放等）
    base_config_file = SUB_DIR / "ponyo.json"
    base_config = {}
    if base_config_file.exists():
        try:
            base_config = json.loads(base_config_file.read_text(encoding="utf-8"))
        except Exception:
            base_config = {}

    # 提取豁免的工具源（豆瓣推荐、配置中心、本地播放等，不计入 30 名额）
    EXEMPT_KEYS = {"drpy_js_豆瓣", "配置中心", "本地"}
    tool_sites = []
    for s in base_config.get("sites", []):
        k = s.get("key", "")
        api = str(s.get("api", ""))
        if k in EXEMPT_KEYS or "csp_Config" in api or "csp_LocalFile" in api:
            tool_sites.append(s)

    # 构建 ponyo-lite.json: 工具源 + 30个计数点播源
    lite_config = base_config.copy()
    lite_config["sites"] = tool_sites + counted_sites
    
    lives_list = []
    if official_live_url := live_res.get("official_url"):
        lives_list = [{
            "name": "Live",
            "type": 0,
            "url": official_live_url,
            "playerType": 1,
            "epg": "http://epg.51zmt.top:8000/api/diyp/"
        }]
    elif base_config.get("lives"):
        lives_list = [base_config["lives"][0]]
        
    lite_config["lives"] = lives_list

    lite_str = json.dumps(lite_config, ensure_ascii=False, indent=2) + "\n"
    lite_bytes = lite_str.encode("utf-8")
    (out_path / "ponyo-lite.json").write_bytes(lite_bytes)

    # 构建 ponyo-live.json
    live_config = base_config.copy()
    live_config["sites"] = []
    live_config["lives"] = lives_list
    live_str = json.dumps(live_config, ensure_ascii=False, indent=2) + "\n"
    live_bytes = live_str.encode("utf-8")
    (out_path / "ponyo-live.json").write_bytes(live_bytes)

    # 构建 ponyo-children.json
    children_config = base_config.copy()
    children_config["sites"] = [children_site] if children_site else []
    children_config["lives"] = []
    children_str = json.dumps(children_config, ensure_ascii=False, indent=2) + "\n"
    children_bytes = children_str.encode("utf-8")
    (out_path / "ponyo-children.json").write_bytes(children_bytes)

    # 3. 生成 ponyo-full.json (所有未被 deny 的源)
    rows_full = con.execute("""
        SELECT r.raw_json, dg.fingerprint
        FROM dedup_group dg
        JOIN raw_source r ON dg.primary_raw_id = r.id
        LEFT JOIN list_state ls ON dg.fingerprint = ls.fingerprint
        WHERE COALESCE(ls.state, 'candidate') != 'deny'
    """).fetchall()

    full_sites = []
    for r in rows_full:
        try:
            full_sites.append(
                _attach_approved_jar(
                    json.loads(r["raw_json"]),
                    r["fingerprint"],
                    approved_jar_urls,
                )
            )
        except Exception:
            pass

    full_config = base_config.copy()
    full_config["sites"] = full_sites
    full_str = json.dumps(full_config, ensure_ascii=False, indent=2) + "\n"
    full_bytes = full_str.encode("utf-8")
    (out_path / "ponyo-full.json").write_bytes(full_bytes)

    # 生成内部候选文件 ponyo-candidates.json (不入 manifest)
    rows_cand = con.execute("""
        SELECT r.raw_json, dg.fingerprint
        FROM dedup_group dg
        JOIN raw_source r ON dg.primary_raw_id = r.id
        LEFT JOIN list_state ls ON dg.fingerprint = ls.fingerprint
        WHERE ls.state = 'candidate'
    """).fetchall()

    cand_sites = []
    for r in rows_cand:
        try:
            cand_sites.append(
                _attach_approved_jar(
                    json.loads(r["raw_json"]),
                    r["fingerprint"],
                    approved_jar_urls,
                )
            )
        except Exception:
            pass
    cand_config = base_config.copy()
    cand_config["sites"] = cand_sites
    cand_str = json.dumps(cand_config, ensure_ascii=False, indent=2) + "\n"
    (out_path / "ponyo-candidates.json").write_bytes(cand_str.encode("utf-8"))

    # 4. 生成 manifest.json
    version_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    manifest = {
        "version": version_id,
        "generated_at": now,
        "source_count": len(lite_config["sites"]),
        "files": {
            "ponyo-lite.json": {"sha256": _calc_sha256(lite_str), "size": len(lite_bytes)},
            "ponyo-full.json": {"sha256": _calc_sha256(full_str), "size": len(full_bytes)},
            "ponyo-live.json": {"sha256": _calc_sha256(live_str), "size": len(live_bytes)},
            "ponyo-children.json": {"sha256": _calc_sha256(children_str), "size": len(children_bytes)},
        }
    }
    manifest_str = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    (out_path / "manifest.json").write_bytes(manifest_str.encode("utf-8"))

    con.close()

    return {
        "version": version_id,
        "lite_sources": len(lite_config["sites"]),
        "full_sources": len(full_sites),
        "output_dir": str(out_path),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DATA_DIR / "sources.db"))
    p.add_argument("--output", default=str(SUB_DIR))
    args = p.parse_args()
    result = generate_all_subscriptions(args.db, output_dir=args.output)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
