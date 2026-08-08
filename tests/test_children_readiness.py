import sqlite3

from ponyo_source_manager.publishing import children_aggregate


def _children_db(path, allow_count):
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE raw_source (id INTEGER PRIMARY KEY, name TEXT, site_key TEXT, api TEXT, ext TEXT);
        CREATE TABLE norm_source (raw_id INTEGER, fingerprint TEXT, category TEXT);
        CREATE TABLE list_state (fingerprint TEXT, state TEXT);
        CREATE TABLE score_snapshot (fingerprint TEXT, total_score REAL, hard_pass INT, scored_at TEXT);
        CREATE TABLE media_probe (fingerprint TEXT, quality_tier TEXT, success INT);
        CREATE TABLE capability_sampling (
            fingerprint TEXT, capability TEXT, hit_count INT
        );
    """)
    for index in range(allow_count):
        fp = f"fp-{index}"
        con.execute("INSERT INTO raw_source VALUES (?, ?, ?, ?, ?)",
                    (index + 1, f"儿童源{index}", f"child-{index}", "api", "ext"))
        con.execute("INSERT INTO norm_source VALUES (?, ?, '儿童')", (index + 1, fp))
        con.execute("INSERT INTO list_state VALUES (?, 'allow')", (fp,))
        con.execute("INSERT INTO score_snapshot VALUES (?, ?, 1, '2026-07-27T00:00:00+00:00')",
                    (fp, 90 - index))
    con.commit()
    con.close()


def test_children_aggregate_requires_two_primary_and_two_backup(tmp_path, monkeypatch):
    db = tmp_path / "children.db"
    _children_db(db, 4)
    monkeypatch.setenv("CHILDREN_API_URL", "https://api.ponyo.fun")
    monkeypatch.setattr(children_aggregate, "_populate_cache_from_sources", lambda *args: None)

    result = children_aggregate.aggregate_children_sources(str(db))
    assert result["ready"] is True
    assert result["primary"] == 2
    assert result["backup"] == 2
    assert result["tvbox_site"]["api"] == "https://api.ponyo.fun"


def test_children_aggregate_does_not_publish_without_four_verified_lines(tmp_path, monkeypatch):
    db = tmp_path / "children.db"
    _children_db(db, 3)
    monkeypatch.setenv("CHILDREN_API_URL", "https://api.ponyo.fun")
    monkeypatch.setattr(children_aggregate, "_populate_cache_from_sources", lambda *args: None)

    result = children_aggregate.aggregate_children_sources(str(db))
    assert result["ready"] is False
    assert result["tvbox_site"] is None


def test_observed_children_capability_is_eligible_without_primary_category(tmp_path, monkeypatch):
    db = tmp_path / "children.db"
    _children_db(db, 4)
    with sqlite3.connect(db) as con:
        con.execute("UPDATE norm_source SET category='影视' WHERE fingerprint='fp-0'")
        con.execute(
            "INSERT INTO capability_sampling VALUES('fp-0','children',3)"
        )
    monkeypatch.setenv("CHILDREN_API_URL", "https://api.ponyo.fun")
    monkeypatch.setattr(children_aggregate, "_populate_cache_from_sources", lambda *_: None)

    result = children_aggregate.aggregate_children_sources(str(db))

    assert result["ready"] is True
    assert result["total_children_sources"] == 4


def test_children_capability_does_not_pull_from_live_quota(tmp_path, monkeypatch):
    db = tmp_path / "children.db"
    _children_db(db, 4)
    with sqlite3.connect(db) as con:
        con.execute("UPDATE norm_source SET category='直播' WHERE fingerprint='fp-0'")
        con.execute(
            "INSERT INTO capability_sampling VALUES('fp-0','children',3)"
        )
    monkeypatch.setenv("CHILDREN_API_URL", "https://api.ponyo.fun")
    monkeypatch.setattr(children_aggregate, "_populate_cache_from_sources", lambda *_: None)

    result = children_aggregate.aggregate_children_sources(str(db))

    assert result["ready"] is False
    assert result["total_children_sources"] == 3
