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
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
SUB_DIR = PROJECT_ROOT / "subscription"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _calc_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def generate_all_subscriptions(db_path: str, *, output_dir: str | Path | None = None,
                               now: str | None = None) -> dict:
    now = now or _now()
    out_path = Path(output_dir) if output_dir else SUB_DIR
    out_path.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row

    # 1. 精选 30 源提取 (按评分排序取前30)
    rows_allow = con.execute("""
        SELECT r.raw_json, s.total_score, n.category
        FROM list_state ls
        JOIN norm_source n ON ls.fingerprint = n.fingerprint
        JOIN raw_source r ON n.raw_id = r.id
        LEFT JOIN score_snapshot s ON n.fingerprint = s.fingerprint
        WHERE ls.state = 'allow'
        ORDER BY s.total_score DESC
        LIMIT 30
    """).fetchall()

    lite_sites = []
    for r in rows_allow:
        try:
            site_obj = json.loads(r["raw_json"])
            lite_sites.append(site_obj)
        except Exception:
            pass

    # 2. 读取基础配置模板（如豆瓣推荐、设置、本地播放等）
    base_config_file = SUB_DIR / "ponyo.json"
    base_config = {}
    if base_config_file.exists():
        try:
            base_config = json.loads(base_config_file.read_text(encoding="utf-8"))
        except Exception:
            base_config = {}

    # 构建 ponyo-lite.json
    lite_config = base_config.copy()
    lite_config["sites"] = lite_sites

    lite_str = json.dumps(lite_config, ensure_ascii=False, indent=2) + "\n"
    (out_path / "ponyo-lite.json").write_text(lite_str, encoding="utf-8")

    # 3. 生成 ponyo-full.json (所有未被 deny 的源)
    rows_full = con.execute("""
        SELECT r.raw_json
        FROM norm_source n
        JOIN raw_source r ON n.raw_id = r.id
        LEFT JOIN list_state ls ON n.fingerprint = ls.fingerprint
        WHERE COALESCE(ls.state, 'candidate') != 'deny'
    """).fetchall()

    full_sites = []
    for r in rows_full:
        try:
            full_sites.append(json.loads(r["raw_json"]))
        except Exception:
            pass

    full_config = base_config.copy()
    full_config["sites"] = full_sites
    full_str = json.dumps(full_config, ensure_ascii=False, indent=2) + "\n"
    (out_path / "ponyo-full.json").write_text(full_str, encoding="utf-8")

    # 4. 生成 manifest.json
    version_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    manifest = {
        "version": version_id,
        "generated_at": now,
        "source_count": len(lite_sites),
        "files": {
            "ponyo-lite.json": {"sha256": _calc_sha256(lite_str), "size": len(lite_str.encode("utf-8"))},
            "ponyo-full.json": {"sha256": _calc_sha256(full_str), "size": len(full_str.encode("utf-8"))},
        }
    }
    manifest_str = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    (out_path / "manifest.json").write_text(manifest_str, encoding="utf-8")

    con.close()

    return {
        "version": version_id,
        "lite_sources": len(lite_sites),
        "full_sources": len(full_sites),
        "output_dir": str(out_path),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(HERE / "data" / "sources.db"))
    p.add_argument("--output", default=str(SUB_DIR))
    args = p.parse_args()
    result = generate_all_subscriptions(args.db, output_dir=args.output)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
