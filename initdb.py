#!/usr/bin/env python3
"""建库：读取 schema.sql 建表（幂等；--reset 重建）。"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA = HERE / "schema.sql"
_EXTRA_SCHEMAS = [
    HERE / "schema_phase3.sql",
    HERE / "schema_phase3c.sql",
    HERE / "schema_phase3d.sql",
    HERE / "schema_phase3e.sql",
]


def init_db(db_path: str, reset: bool = False) -> None:
    path = Path(db_path)
    if reset and path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    ddl = SCHEMA.read_text(encoding="utf-8")
    con = sqlite3.connect(str(path))
    try:
        con.executescript(ddl)
        for extra in _EXTRA_SCHEMAS:
            if extra.exists():
                con.executescript(extra.read_text(encoding="utf-8"))
        con.commit()
    finally:
        con.close()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(HERE / "data" / "sources.db"))
    p.add_argument("--reset", action="store_true")
    args = p.parse_args()
    init_db(args.db, reset=args.reset)
    print(f"initialized {args.db}")


if __name__ == "__main__":
    main()
