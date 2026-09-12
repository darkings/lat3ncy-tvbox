#!/usr/bin/env python3
"""把订阅中相对路径的 api/ext 依赖下载到发布仓库，保持相对路径可用。"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlsplit

from ponyo_source_manager.core import net
from ponyo_source_manager.core.common import DATA_DIR
from ponyo_source_manager.discovery.path_resolver import is_relative_asset, resolve_asset_url


def _site_origins(db_path: str) -> dict[str, str]:
    """site_key -> origin（取 dedup_group.primary_raw_id 对应 raw_source.origin）"""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT r.site_key, r.origin
        FROM dedup_group dg
        JOIN raw_source r ON r.id = dg.primary_raw_id
        WHERE r.site_key IS NOT NULL AND r.origin IS NOT NULL
        GROUP BY r.site_key
        HAVING r.id = MIN(r.id)
        """
    ).fetchall()
    con.close()
    return {r["site_key"]: r["origin"] for r in rows}


def _safe_rel_path(value: str) -> Path | None:
    """把 ./libs/tv/zb.min.js 转成安全相对路径 libs/tv/zb.min.js，拒绝 ../ 等逃逸。"""
    v = value.strip().lstrip("./")
    if not v or ".." in v.split("/"):
        return None
    # 只允许字母数字、中文、常见符号
    parts = [p for p in v.split("/") if p]
    if not parts:
        return None
    return Path(*parts)


def materialize(subscription_path: Path, db_path: str, output_root: Path) -> dict:
    data = json.loads(subscription_path.read_text(encoding="utf-8"))
    sites = data.get("sites", [])
    origins = _site_origins(db_path)

    downloaded: list[dict] = []
    failed: list[dict] = []
    skipped: list[dict] = []

    for site in sites:
        key = site.get("key", "")
        origin = origins.get(key)
        if not origin:
            skipped.append({"key": key, "reason": "no origin"})
            continue

        for field in ("api", "ext"):
            value = site.get(field)
            if not isinstance(value, str) or not is_relative_asset(value):
                continue
            resolved, status = resolve_asset_url(origin, value)
            if status != "resolved" or not resolved:
                failed.append({"key": key, "field": field, "value": value, "reason": status})
                continue

            rel = _safe_rel_path(value)
            if rel is None:
                failed.append({"key": key, "field": field, "value": value, "reason": "unsafe_path"})
                continue

            target = output_root / rel
            if target.is_file():
                skipped.append({"key": key, "field": field, "value": value, "reason": "exists"})
                continue

            try:
                blob = net.fetch_bytes(resolved, timeout=30.0, max_bytes=8 * 1024 * 1024)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(blob)
                downloaded.append({
                    "key": key,
                    "field": field,
                    "value": value,
                    "url": resolved,
                    "path": str(rel),
                    "size": len(blob),
                })
            except Exception as exc:
                failed.append({
                    "key": key,
                    "field": field,
                    "value": value,
                    "url": resolved,
                    "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                })

    return {"downloaded": downloaded, "failed": failed, "skipped": skipped}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--subscription", required=True, help="生成的 ponyo.json 路径")
    p.add_argument("--db", default=str(DATA_DIR / "sources.db"))
    p.add_argument("--output", required=True, help="发布仓库 subscription 目录")
    args = p.parse_args()

    result = materialize(
        Path(args.subscription),
        args.db,
        Path(args.output),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()

