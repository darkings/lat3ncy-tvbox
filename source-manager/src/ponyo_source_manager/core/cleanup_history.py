#!/usr/bin/env python3
"""清理指纹与历史记录 (历史指纹因规则变化失效)。
此脚本将：
1. 备份现有 sources.db
2. 删除所有派生数据 (norm_source, list_state, score_snapshot, conn_probe, 等)
3. 重新规范化 raw_source 中的所有数据，生成新指纹并设置为 candidate 状态。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ponyo_source_manager.core.common import DATA_DIR, CONFIG_DIR, compute_fingerprint, classify


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def cleanup_and_rebuild(db_path: str, policy_path: str) -> None:
    now = _now()
    db = Path(db_path)
    if not db.exists():
        print(f"DB {db_path} does not exist.")
        return

    # 1. 备份
    backup_path = db.with_suffix(".db.bak")
    shutil.copy2(db, backup_path)
    print(f"Backed up DB to {backup_path}")

    con = sqlite3.connect(str(db))
    policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))

    try:
        con.execute("BEGIN TRANSACTION")

        # 2. 清空所有派生数据表
        tables_to_clear = [
            "norm_source",
            "list_state",
            "score_snapshot",
            "conn_probe",
            "security_finding",
            "drpy_test_result",
            "media_probe",
            "promotion_log"
        ]
        for tbl in tables_to_clear:
            try:
                con.execute(f"DELETE FROM {tbl}")
            except sqlite3.OperationalError:
                pass  # Ignore if table doesn't exist
        print("Cleared derived tables.")

        # 3. 读取 raw_source，重新计算指纹并插入 norm_source
        rows = con.execute("SELECT id, raw_json, name FROM raw_source").fetchall()
        for raw_id, raw_json, site_name in rows:
            site = json.loads(raw_json)
            fp, meta = compute_fingerprint(site)
            category = classify(site_name, policy)

            con.execute(
                "INSERT OR IGNORE INTO norm_source"
                "(raw_id, fingerprint, api_host, required_urls, jar_md5, spider_class, category, capabilities)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (raw_id, fp, meta["api_host"], json.dumps(meta["required_urls"], ensure_ascii=False),
                 meta["jar_md5"], meta["spider_class"], category, json.dumps([], ensure_ascii=False))
            )

            # 4. 设为 candidate 候选状态
            con.execute(
                "INSERT OR IGNORE INTO list_state(fingerprint, state, reason, updated_at)"
                " VALUES(?,?,?,?)",
                (fp, "candidate", "history_rebuild", now)
            )

        con.commit()
        print(f"Rebuilt {len(rows)} sources with new fingerprints.")
    except Exception as e:
        con.rollback()
        print(f"Failed: {e}")
        raise
    finally:
        con.close()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DATA_DIR / "sources.db"))
    p.add_argument("--policy", default=str(CONFIG_DIR / "policy.json"))
    args = p.parse_args()
    cleanup_and_rebuild(args.db, args.policy)


if __name__ == "__main__":
    main()
