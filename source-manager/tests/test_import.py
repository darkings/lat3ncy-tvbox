import json
import sqlite3
from pathlib import Path

import pytest

from ponyo_source_manager.core.initdb import init_db
from ponyo_source_manager.discovery.import_sources import import_all

SOURCE_MANAGER_DIR = Path(__file__).resolve().parents[1]
POLICY = SOURCE_MANAGER_DIR / "config" / "policy.json"


def _mk_inputs(tmp_path, sites):
    ponyo = tmp_path / "ponyo.json"
    ponyo.write_text(json.dumps({"sites": sites}, ensure_ascii=False), encoding="utf-8")
    health = tmp_path / "health.json"
    health.write_text(json.dumps({"sites": [
        {"index": i, "key": s["key"], "name": s["name"],
         "verdict": "verified", "urls": []} for i, s in enumerate(sites)]},
        ensure_ascii=False), encoding="utf-8")
    namemap = tmp_path / "namemap.json"
    namemap.write_text(json.dumps([
        {"key": s["key"], "old": s["name"], "new": s["name"], "verdict": "verified"}
        for s in sites], ensure_ascii=False), encoding="utf-8")
    return ponyo, health, namemap


def test_import_counts(tmp_path, sites):
    db = tmp_path / "t.db"
    init_db(str(db))
    ponyo, health, namemap = _mk_inputs(tmp_path, sites)
    counts = import_all(str(db), str(ponyo), str(health), str(namemap),
                        str(POLICY), batch="B1")
    assert counts["raw"] == len(sites)
    assert counts["health"] == len(sites)
    assert counts["name_map"] == len(sites)
    con = sqlite3.connect(str(db))
    assert con.execute("SELECT count(*) FROM raw_source").fetchone()[0] == len(sites)
    assert con.execute("SELECT count(*) FROM norm_source").fetchone()[0] == len(sites)
    con.close()


def test_import_idempotent_same_batch(tmp_path, sites):
    db = tmp_path / "t.db"
    init_db(str(db))
    ponyo, health, namemap = _mk_inputs(tmp_path, sites)
    import_all(str(db), str(ponyo), str(health), str(namemap), str(POLICY), batch="B1")
    import_all(str(db), str(ponyo), str(health), str(namemap), str(POLICY), batch="B1")
    con = sqlite3.connect(str(db))
    # 同 batch 重跑 raw 不翻倍（INSERT OR IGNORE + UNIQUE 约束）
    assert con.execute("SELECT count(*) FROM raw_source").fetchone()[0] == len(sites)
    con.close()


def test_list_state_all_candidate(tmp_path, sites):
    db = tmp_path / "t.db"
    init_db(str(db))
    ponyo, health, namemap = _mk_inputs(tmp_path, sites)
    import_all(str(db), str(ponyo), str(health), str(namemap), str(POLICY), batch="B1")
    con = sqlite3.connect(str(db))
    total = con.execute("SELECT count(*) FROM list_state").fetchone()[0]
    cand = con.execute("SELECT count(*) FROM list_state WHERE state='candidate'").fetchone()[0]
    con.close()
    assert total == cand and total > 0


def test_category_assigned(tmp_path, sites):
    db = tmp_path / "t.db"
    init_db(str(db))
    ponyo, health, namemap = _mk_inputs(tmp_path, sites)
    import_all(str(db), str(ponyo), str(health), str(namemap), str(POLICY), batch="B1")
    con = sqlite3.connect(str(db))
    cats = dict(con.execute(
        "SELECT r.name, n.category FROM norm_source n JOIN raw_source r ON n.raw_id=r.id"))
    con.close()
    assert cats["夸克网盘"] == "网盘"
    assert cats["宝宝巴士儿童"] == "儿童"


def test_empty_sites_raises(tmp_path):
    db = tmp_path / "t.db"
    init_db(str(db))
    ponyo, health, namemap = _mk_inputs(tmp_path, [])
    with pytest.raises(ValueError):
        import_all(str(db), str(ponyo), str(health), str(namemap), str(POLICY), batch="B1")
