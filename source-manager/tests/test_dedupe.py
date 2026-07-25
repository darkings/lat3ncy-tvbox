import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from initdb import init_db
from import_sources import import_all
from dedupe import run_dedupe

PROJECT = Path(__file__).resolve().parents[2]
POLICY = PROJECT / "source-manager" / "config" / "policy.json"


def _mk_inputs(tmp_path, sites):
    ponyo = tmp_path / "ponyo.json"
    ponyo.write_text(json.dumps({"sites": sites}, ensure_ascii=False), encoding="utf-8")
    health = tmp_path / "health.json"
    health.write_text(json.dumps({"sites": [
        {"index": i, "key": s["key"], "name": s["name"],
         "verdict": "verified", "urls": []} for i, s in enumerate(sites)]},
        ensure_ascii=False), encoding="utf-8")
    namemap = tmp_path / "namemap.json"
    namemap.write_text(json.dumps([], ensure_ascii=False), encoding="utf-8")
    return ponyo, health, namemap


def _prepare(tmp_path, sites):
    db = tmp_path / "t.db"
    init_db(str(db))
    ponyo, health, namemap = _mk_inputs(tmp_path, sites)
    import_all(str(db), str(ponyo), str(health), str(namemap), str(POLICY), batch="B1")
    report = tmp_path / "rep.json"
    result = run_dedupe(str(db), str(POLICY), str(report))
    return db, report, result


def test_groups_merge_known_duplicates(tmp_path, sites):
    # sites 中 s0/s1 同指纹、s2/s3 同指纹 → 8 条 → 6 组
    _, _, result = _prepare(tmp_path, sites)
    assert result["total"] == 8
    assert result["groups"] == 6
    assert result["duplicates"] == 2


def test_dedup_group_rows(tmp_path, sites):
    db, _, _ = _prepare(tmp_path, sites)
    con = sqlite3.connect(str(db))
    rows = con.execute(
        "SELECT member_count FROM dedup_group ORDER BY member_count DESC").fetchall()
    con.close()
    assert rows[0][0] == 2  # 最大组含 2 成员


def test_report_written(tmp_path, sites):
    _, report, _ = _prepare(tmp_path, sites)
    doc = json.loads(report.read_text(encoding="utf-8"))
    assert doc["total"] == 8 and doc["groups"] == 6
    assert len(doc["details"]) == 6
    dup = [d for d in doc["details"] if d["member_count"] == 2]
    assert len(dup) == 2
    # primary 必须是本组成员之一（norm_id 层面）
    assert all(len(d["members_ids"]) == 2 for d in dup)


def test_dedupe_idempotent(tmp_path, sites):
    db, report, _ = _prepare(tmp_path, sites)
    r2 = run_dedupe(str(db), str(POLICY), str(report))
    con = sqlite3.connect(str(db))
    n = con.execute("SELECT count(*) FROM dedup_group").fetchone()[0]
    con.close()
    assert n == 6 and r2["groups"] == 6
