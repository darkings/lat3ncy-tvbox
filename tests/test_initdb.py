import sqlite3
from pathlib import Path

from ponyo_source_manager.core.initdb import init_db

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


def test_migration_v5_to_v6_adds_hard_pass(tmp_path):
    db = tmp_path / "v5_old.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE schema_version (version INT PRIMARY KEY, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    con.execute("INSERT INTO schema_version (version) VALUES (1), (2), (3), (4), (5)")
    con.execute("""
        CREATE TABLE score_snapshot (
            id INTEGER PRIMARY KEY,
            fingerprint TEXT NOT NULL,
            timeslot TEXT,
            total_score REAL NOT NULL,
            scored_at TEXT NOT NULL
        )
    """)
    con.commit()
    con.close()

    # 执行迁移升级
    init_db(str(db))

    con = sqlite3.connect(str(db))
    versions = [r[0] for r in con.execute("SELECT version FROM schema_version ORDER BY version").fetchall()]
    cols = [r[1] for r in con.execute("PRAGMA table_info(score_snapshot)").fetchall()]
    con.close()

    assert 6 in versions
    assert "hard_pass" in cols

    # 再次升级验证幂等性
    init_db(str(db))
    con = sqlite3.connect(str(db))
    cols_after = [r[1] for r in con.execute("PRAGMA table_info(score_snapshot)").fetchall()]
    con.close()
    assert cols_after.count("hard_pass") == 1

