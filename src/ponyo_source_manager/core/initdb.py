#!/usr/bin/env python3
"""建库与迁移：支持按版本进行 Schema 迁移，支持回滚。"""
from __future__ import annotations

import argparse
import sqlite3
import os
from pathlib import Path

from ponyo_source_manager.core.common import PONYO_ROOT, DATA_DIR, CODE_DIR

MIGRATIONS_DIR = CODE_DIR / "db" / "migrations"


def init_db(db_path: str, reset: bool = False) -> None:
    path = Path(db_path)
    if reset and path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    
    con = sqlite3.connect(str(path))
    try:
        # Check if schema_version exists, if not but norm_source exists, it's an old DB (version 1)
        version_row = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'").fetchone()
        if not version_row:
            con.execute("CREATE TABLE schema_version (version INT PRIMARY KEY, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            has_norm = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='norm_source'").fetchone()
            if has_norm:
                # 已经是基于 schema*.sql 的旧库，假设 version=1
                con.execute("INSERT INTO schema_version (version) VALUES (1)")
            else:
                con.execute("INSERT INTO schema_version (version) VALUES (0)")
        
        current_version = con.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] or 0
        
        # 读取并按顺序执行 migration 脚本
        if MIGRATIONS_DIR.exists():
            files = sorted(MIGRATIONS_DIR.glob("*.sql"))
            for f in files:
                try:
                    v = int(f.name.split("_")[0])
                except ValueError:
                    continue
                    
                if v > current_version:
                    print(f"Applying migration: {f.name}")
                    try:
                        sql_content = f.read_text(encoding="utf-8")
                        con.executescript(sql_content)
                        con.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
                        con.commit()
                        current_version = v
                    except sqlite3.OperationalError as e:
                        if "duplicate column name" in str(e).lower():
                            con.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
                            con.commit()
                            current_version = v
                        else:
                            con.rollback()
                            print(f"Migration {f.name} failed: {e}")
                            raise
                    except Exception as e:
                        con.rollback()
                        print(f"Migration {f.name} failed: {e}")
                        raise

        # 防御性确保 score_snapshot 存在时一定有 hard_pass 字段
        has_score = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='score_snapshot'").fetchone()
        if has_score:
            cols = [r[1] for r in con.execute("PRAGMA table_info(score_snapshot)").fetchall()]
            if "hard_pass" not in cols:
                con.execute("ALTER TABLE score_snapshot ADD COLUMN hard_pass INT DEFAULT 0")
                con.commit()

        # media_probe was introduced after some production/legacy databases.
        # Add duration-gate fields defensively so upgrades stay idempotent and
        # partial legacy databases without this table can still be migrated.
        has_media_probe = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='media_probe'"
        ).fetchone()
        if has_media_probe:
            media_cols = {
                r[1] for r in con.execute("PRAGMA table_info(media_probe)").fetchall()
            }
            duration_columns = {
                "content_type": "TEXT NOT NULL DEFAULT 'unknown'",
                "min_duration_s": "REAL NOT NULL DEFAULT 30",
                "duration_pass": "INT NOT NULL DEFAULT 0",
                "duration_reason": "TEXT",
                "ffprobe_success": "INT NOT NULL DEFAULT 0",
            }
            for column, definition in duration_columns.items():
                if column not in media_cols:
                    con.execute(
                        f"ALTER TABLE media_probe ADD COLUMN {column} {definition}"
                    )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_duration_gate "
                "ON media_probe(fingerprint, duration_pass, probed_at)"
            )
            con.commit()
    finally:
        con.close()


def main() -> None:

    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DATA_DIR / "sources.db"))
    p.add_argument("--reset", action="store_true")
    args = p.parse_args()
    init_db(args.db, reset=args.reset)
    print(f"initialized {args.db}")


if __name__ == "__main__":
    main()
