import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from initdb import init_db

EXPECTED_TABLES = {"raw_source", "norm_source", "dedup_group",
                   "health_snapshot", "name_map", "list_state"}


def _tables(db):
    con = sqlite3.connect(db)
    rows = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    con.close()
    return {r[0] for r in rows}


def test_init_creates_six_tables(tmp_path):
    db = tmp_path / "t.db"
    init_db(str(db))
    assert EXPECTED_TABLES <= _tables(str(db))


def test_init_idempotent(tmp_path):
    db = tmp_path / "t.db"
    init_db(str(db))
    init_db(str(db))  # 第二次不报错
    assert EXPECTED_TABLES <= _tables(str(db))


def test_reset_recreates(tmp_path):
    db = tmp_path / "t.db"
    init_db(str(db))
    con = sqlite3.connect(str(db))
    con.execute("INSERT INTO name_map(site_key) VALUES('x')")
    con.commit(); con.close()
    init_db(str(db), reset=True)
    con = sqlite3.connect(str(db))
    n = con.execute("SELECT count(*) FROM name_map").fetchone()[0]
    con.close()
    assert n == 0


def test_initdb_creates_phase3_tables(tmp_path):
    db = tmp_path / "s.db"
    init_db(str(db))
    import sqlite3
    con = sqlite3.connect(str(db))
    names = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert {"security_finding", "conn_probe"} <= names
